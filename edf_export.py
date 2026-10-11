"""EDF export (MNE/edfio) and read-back checks. EDF stores quantized samples."""
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


def export_edf_checked(raw, source_path, destination_dir):
    """Export an EEG-only Raw; report what survived EDF round trip.

    Returns (edf_path, report). REVIEW rather than PASS if a supported check fails.
    Does not overwrite existing outputs. Original Raw is never modified.
    """
    try:
        import edfio  # noqa: F401  (required internally by MNE)
    except ImportError as exc:
        raise RuntimeError('EDF export requires edfio. Run: .venv\\Scripts\\python.exe -m pip install edfio') from exc
    import mne

    source_path, destination_dir = Path(source_path), Path(destination_dir)
    if not destination_dir.is_dir():
        raise ValueError('Output folder does not exist.')
    if not raw.ch_names or any(t != 'eeg' for t in raw.get_channel_types()):
        raise ValueError('EDF export currently requires EEG-only recordings.')
    out = destination_dir / (source_path.stem.replace('-raw', '') + '_converted.edf')
    validation_path = out.with_name(out.stem + '_validation.json')
    if out.exists() or validation_path.exists():
        raise FileExistsError(f'EDF or validation report already exists: {out}. Choose a new output folder.')
    fs = float(raw.info['sfreq'])
    # EDF has a fixed-width header and fixed samples per data record.
    # MNE may pad exports to a whole second when n_times / sfreq is not an integer.
    # Expose this rather than silently treating padded data as identical.
    if not np.isclose(fs, round(fs), atol=1e-9, rtol=0):
        raise ValueError('This EDF export supports integer-valued sampling rates only; resampling is not performed.')
    if raw.n_times % int(round(fs)) != 0:
        raise ValueError('This EDF export requires whole-second recordings to avoid silent sample padding. Crop or choose FIF/CSV.')
    # EDF labels are 16 ASCII bytes maximum. Avoid silent truncation/renaming.
    for name in raw.ch_names:
        if len(name.encode('ascii', 'ignore')) != len(name) or len(name.encode('ascii')) > 16:
            raise ValueError(f'EDF channel label must be ASCII and at most 16 bytes: {name!r}. Choose FIF/CSV.')

    created = []
    try:
        raw.load_data()
        mne.export.export_raw(str(out), raw, fmt='edf', physical_range='auto', add_ch_type=False,
                              overwrite=False, verbose='ERROR')
        created.append(out)
        converted = mne.io.read_raw_edf(str(out), preload=True, verbose='ERROR')
        names_match = converted.ch_names == raw.ch_names
        samples_match = converted.n_times == raw.n_times
        rate_match = bool(np.isclose(converted.info['sfreq'], fs, rtol=0, atol=1e-9))
        eeg_types_match = converted.get_channel_types() == raw.get_channel_types()

        # 16-bit EDF quantization error scales with each signal's saved digital step.
        # Compute per-channel digital quantization step based on the readable EDF data
        # range; 1 microvolt absolute lower bound accommodates header rounding.
        original_uv = raw.get_data() * 1e6
        restored_uv = converted.get_data() * 1e6
        comparable = names_match and samples_match and original_uv.shape == restored_uv.shape
        if comparable:
            diff = restored_uv - original_uv
            max_error = float(np.max(np.abs(diff))) if diff.size else 0.0
            rmse = float(np.sqrt(np.mean(np.square(diff)))) if diff.size else 0.0
            # Tolerance is explicitly a bounded engineering check, not lossless equivalence.
            # 0.5% of each channel's peak-to-peak signal range (min 1 uV).
            ptp = np.ptp(original_uv, axis=1)
            tolerance = np.maximum(1.0, 0.005 * ptp)
            signal_close = bool(np.all(np.abs(diff) <= tolerance[:, None]))
            tol_max = float(tolerance.max())
        else:
            max_error = rmse = tol_max = None
            signal_close = False

        src_ann = raw.annotations
        dst_ann = converted.annotations
        annotation_count_match = len(src_ann) == len(dst_ann)
        descriptions_match = annotation_count_match and list(src_ann.description) == list(dst_ann.description)
        # EDF+ annotations may be limited by timing precision; 10ms is explicit.
        onset_match = bool(annotation_count_match and np.allclose(src_ann.onset, dst_ann.onset, rtol=0, atol=0.01))
        duration_match = bool(annotation_count_match and np.allclose(src_ann.duration, dst_ann.duration, rtol=0, atol=0.01))
        signal_checks = {'channel_order_match': names_match, 'samples_match': samples_match,
                         'sampling_rate_match': rate_match, 'eeg_channel_types_match': eeg_types_match,
                         'within_edf_tolerance': signal_close,
                         'max_absolute_error_uv': max_error, 'rmse_uv': rmse,
                         'values_compared': int(original_uv.size) if comparable else 0,
                         'maximum_per_channel_tolerance_uv': tol_max}
        annotation_checks = {'count_match': annotation_count_match, 'descriptions_match': bool(descriptions_match),
                             'onsets_match_within_10ms': onset_match, 'durations_match_within_10ms': duration_match}
        overall = bool(all((names_match, samples_match, rate_match, eeg_types_match, signal_close,
                            annotation_count_match, descriptions_match, onset_match, duration_match)))
        report = {
            'version': '0.4.0', 'output_format': 'EDF',
            'timestamp_utc': datetime.now(timezone.utc).isoformat(),
            'source': source_path.name, 'output': out.name,
            'report_file': validation_path.name,
            'files': [out.name, validation_path.name],
            'signal_validation': signal_checks,
            'annotation_validation': annotation_checks,
            'metadata_validation': {'core_sampling_rate_match': rate_match, 'channel_names_match': names_match},
            'overall_validation_passed': overall,
            'full_metadata_equivalence': 'NOT_VERIFIED',
            'edf_waveform_precision': '16-bit quantized: NOT LOSSLESS',
            'limitations': ('Signal tolerance: max(1 uV, 0.5% of each channel peak-to-peak); '
                            'this is a coarse acceptance threshold, not a guarantee of clinically adequate fidelity. '
                            'EDF header, sensor positions, measurement date, and all internal MNE fields are not '
                            'validated. EDF+ event checks cover only MNE annotations, not stim triggers.')
        }
        validation_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False), encoding='utf-8')
        created.append(validation_path)
        return out, report
    except Exception:
        for path in created + [out]:
            if path.exists():
                path.unlink()
        raise
