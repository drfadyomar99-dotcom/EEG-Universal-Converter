"""Explicit, verified continuous EEG export paths. Not a universal lossless converter."""
import json
from pathlib import Path
from datetime import datetime, timezone
import numpy as np
import mne
from scipy.io import savemat, loadmat

FORMATS = {'FIF': '.fif', 'EDF': '.edf', 'EEGLAB SET': '.set', 'BrainVision VHDR': '.vhdr', 'MAT': '.mat'}

def read_mat(path):
    """Read this application's own structured MAT export, not arbitrary MATLAB datasets."""
    d = loadmat(str(path), squeeze_me=True)
    required = ('eeg_data_volts', 'sampling_rate_hz', 'channel_names')
    if not all(k in d for k in required):
        raise ValueError('Arbitrary MAT layouts are ambiguous. This reader accepts MAT files exported by this application with eeg_data_volts, sampling_rate_hz, channel_names.')
    values = np.asarray(d['eeg_data_volts'], dtype=np.float64)
    if values.ndim != 2 or not np.isfinite(values).all():
        raise ValueError('MAT EEG data must be a finite 2D channels x samples matrix.')
    fs = float(np.asarray(d['sampling_rate_hz']).item())
    names = [str(x).strip() for x in np.atleast_1d(d['channel_names']).flatten()]
    if not np.isfinite(fs) or fs <= 0 or len(names) != values.shape[0]:
        raise ValueError('Invalid MAT sampling rate or channel names.')
    raw = mne.io.RawArray(values, mne.create_info(names, fs, ch_types='eeg'), verbose='ERROR')
    if all(k in d for k in ('annotation_onsets_s','annotation_durations_s','annotation_descriptions')):
        ons = np.atleast_1d(d['annotation_onsets_s']).astype(float).flatten()
        dur = np.atleast_1d(d['annotation_durations_s']).astype(float).flatten()
        desc = [str(v) for v in np.atleast_1d(d['annotation_descriptions']).flatten()]
        if len(ons) == len(dur) == len(desc) and len(ons):
            raw.set_annotations(mne.Annotations(ons, dur, desc))
    return raw

def export_checked(raw, source_path, destination_dir, label):
    if label not in FORMATS:
        raise ValueError('Unsupported output format: ' + label)
    if any(t != 'eeg' for t in raw.get_channel_types()):
        raise ValueError('Current export paths accept EEG-only recordings.')
    folder = Path(destination_dir); src = Path(source_path)
    if not folder.is_dir():
        raise ValueError('Output directory does not exist.')
    suffix = FORMATS[label]
    stem = src.stem.replace('-raw','') + '_converted'
    out = folder / (stem + ('_raw.fif' if label == 'FIF' else suffix))
    report_path = folder / (stem + '_' + label.lower().replace(' ','_') + '_validation.json')
    # BrainVision writes a three-file family; EEGLAB may create a .fdt partner.
    if out.exists() or report_path.exists() or any(folder.glob(stem + '.*')) or any(folder.glob(stem + '_raw.fif')):
        raise FileExistsError('Output or its companion files already exist. Choose a new folder: ' + str(out))
    fs = float(raw.info['sfreq'])
    raw.load_data()
    original = raw.get_data()
    before = set(folder.iterdir())
    try:
        if label == 'FIF':
            raw.save(str(out), overwrite=False, verbose='ERROR')
            restored = mne.io.read_raw_fif(str(out), preload=True, verbose='ERROR')
        elif label == 'EDF':
            raise ValueError('EDF uses the dedicated, quantization-aware export path.')
        elif label == 'EEGLAB SET':
            try:
                import eeglabio # noqa: F401
            except ImportError as exc:
                raise RuntimeError('EEGLAB export requires: python -m pip install eeglabio') from exc
            mne.export.export_raw(str(out), raw, fmt='eeglab', overwrite=False, verbose='ERROR')
            restored = mne.io.read_raw_eeglab(str(out), preload=True, verbose='ERROR')
        elif label == 'BrainVision VHDR':
            try:
                import pybv # noqa: F401
            except ImportError as exc:
                raise RuntimeError('BrainVision export requires: python -m pip install pybv') from exc
            mne.export.export_raw(str(out), raw, fmt='brainvision', overwrite=False, verbose='ERROR')
            restored = mne.io.read_raw_brainvision(str(out), preload=True, verbose='ERROR')
        elif label == 'MAT':
            ann = raw.annotations
            savemat(str(out), {
                'eeg_data_volts': original, 'sampling_rate_hz': fs,
                'channel_names': np.asarray(raw.ch_names, dtype=object),
                'annotation_onsets_s': np.asarray(ann.onset, dtype=float),
                'annotation_durations_s': np.asarray(ann.duration, dtype=float),
                'annotation_descriptions': np.asarray(list(ann.description), dtype=object),
                'source_filename': src.name, 'units': 'V',
            }, do_compression=True)
            restored = read_mat(out)
        else:
            raise ValueError('Unknown target.')
        names_match = raw.ch_names == restored.ch_names
        sample_match = int(raw.n_times) == int(restored.n_times)
        sfreq_match = bool(np.isclose(fs, float(restored.info['sfreq']), rtol=0, atol=1e-7))
        compatible = original.shape == restored.get_data().shape
        if compatible:
            diff = (original - restored.get_data()) * 1e6
            max_err = float(np.max(np.abs(diff))) if diff.size else 0.0
            rmse = float(np.sqrt(np.mean(diff**2))) if diff.size else 0.0
            # The export backends and float32 representation may introduce small rounding.
            near = bool(np.allclose(original * 1e6, restored.get_data() * 1e6, rtol=1e-6, atol=1e-3))
        else:
            max_err = rmse = None; near = False
        a, b = raw.annotations, restored.annotations
        cnt = len(a) == len(b)
        labels = cnt and list(a.description) == list(b.description)
        onsets = bool(cnt and np.allclose(a.onset,b.onset,rtol=0,atol=0.01))
        durations = bool(cnt and np.allclose(a.duration,b.duration,rtol=0,atol=0.01))
        checks = dict(channel_order_match=names_match, samples_match=sample_match,
                      sampling_rate_match=sfreq_match, all_values_close=near,
                      max_absolute_error_uv=max_err, rmse_uv=rmse,
                      values_compared=int(original.size) if compatible else 0,
                      rtol=1e-6, atol_uv=1e-3)
        events = dict(count_match=cnt, descriptions_match=bool(labels), onsets_match_within_10ms=onsets,
                      durations_match_within_10ms=durations)
        created = sorted(p.name for p in set(folder.iterdir()) - before if p.is_file())
        report = dict(version='0.4.1', timestamp_utc=datetime.now(timezone.utc).isoformat(),
                      output_format=label, source=src.name, output=out.name,
                      signal_validation=checks, annotation_validation=events,
                      metadata_validation={'channel_names_match':names_match,'sampling_rate_match':sfreq_match},
                      overall_validation_passed=bool(all((names_match,sample_match,sfreq_match,near,cnt,labels,onsets,durations))),
                      full_metadata_equivalence='NOT_VERIFIED',
                      limitations='Only implemented checks; no claim of full metadata/geometry/stim preservation. MAT reader is limited to this app schema.',
                      files=created+[report_path.name])
        report_path.write_text(json.dumps(report,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8')
        return out, report
    except Exception:
        for p in set(folder.iterdir()) - before:
            if p.is_file():
                p.unlink()
        raise
