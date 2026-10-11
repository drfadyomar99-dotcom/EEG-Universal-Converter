"""EEG Universal Converter v0.3.4: CSV research bundle and round-trip validation."""
import json
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd


def _json_safe(value):
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return [_json_safe(v) for v in value.tolist()]
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if hasattr(value, 'isoformat'):
        return value.isoformat()
    return str(value)


def _check_events(raw, events_path):
    ann = raw.annotations
    exported = pd.read_csv(events_path, keep_default_na=False)
    expected_columns = ['onset_sec', 'duration_sec', 'description']
    fields = list(exported.columns) == expected_columns
    count = len(exported) == len(ann)
    if not fields or not count:
        return {'columns_match': fields, 'count_match': count, 'onsets_match': False,
                'durations_match': False, 'descriptions_match': False, 'max_timing_error_sec': None}
    onsets = exported['onset_sec'].to_numpy(dtype=float)
    durations = exported['duration_sec'].to_numpy(dtype=float)
    onset_err = float(np.max(np.abs(onsets - ann.onset))) if len(ann) else 0.0
    duration_err = float(np.max(np.abs(durations - ann.duration))) if len(ann) else 0.0
    descriptions = exported['description'].astype(str).tolist()
    return {'columns_match': True, 'count_match': True,
            'onsets_match': bool(np.allclose(onsets, ann.onset, rtol=0, atol=1e-9)),
            'durations_match': bool(np.allclose(durations, ann.duration, rtol=0, atol=1e-9)),
            'descriptions_match': descriptions == list(map(str, ann.description)),
            'max_timing_error_sec': max(onset_err, duration_err)}


def _check_metadata(raw, metadata_path):
    meta = json.loads(metadata_path.read_text(encoding='utf-8'))
    measured = _json_safe(raw.info.get('meas_date'))
    return {
        'channel_names_match': meta.get('channel_names') == list(raw.ch_names),
        'individual_channel_types_match': meta.get('individual_channel_types') == dict(zip(raw.ch_names, raw.get_channel_types())),
        'sampling_rate_match': meta.get('sampling_rate_hz') == float(raw.info['sfreq']),
        'n_samples_match': meta.get('n_samples') == int(raw.n_times),
        'n_channels_match': meta.get('n_channels') == len(raw.ch_names),
        'first_sample_index_match': meta.get('first_sample_index') == int(raw.first_samp),
        'measurement_date_match': meta.get('measurement_date') == measured,
        'signal_units_recorded': meta.get('signal_units') == 'microvolt',
        'highpass_match': meta.get('highpass_hz') == _json_safe(raw.info.get('highpass')),
        'lowpass_match': meta.get('lowpass_hz') == _json_safe(raw.info.get('lowpass')),
    }


def _check_signals(raw, signals_path, chunk_rows=4000):
    """Read CSV in batches; compare all samples in uV in recorded channel order."""
    names = list(raw.ch_names)
    header = list(pd.read_csv(signals_path, nrows=0).columns)
    names_match = header == names
    if not names_match:
        return {'channel_order_match': False, 'samples_match': False, 'all_values_finite': False,
                'all_values_close': False, 'max_absolute_error_uv': None, 'rmse_uv': None,
                'values_compared': 0, 'rtol': 1e-7, 'atol_uv': 1e-6}
    n = 0
    max_error = 0.0
    squared_error = 0.0
    finite = True
    close = True
    values = 0
    for frame in pd.read_csv(signals_path, chunksize=chunk_rows):
        rows = len(frame)
        if n + rows > raw.n_times:
            close = False
            break
        actual = frame.to_numpy(dtype=np.float64).T
        expected = raw.get_data(start=n, stop=n+rows) * 1e6
        if not np.isfinite(actual).all() or not np.isfinite(expected).all():
            finite = False
            close = False
            break
        diff = actual - expected
        max_error = max(max_error, float(np.max(np.abs(diff)))) if diff.size else max_error
        squared_error += float(np.sum(np.square(diff, dtype=np.float64), dtype=np.float64))
        values += diff.size
        close = close and bool(np.allclose(actual, expected, rtol=1e-7, atol=1e-6))
        n += rows
    samples_match = n == raw.n_times
    return {'channel_order_match': names_match, 'samples_match': samples_match,
            'all_values_finite': finite, 'all_values_close': bool(close and samples_match and finite),
            'max_absolute_error_uv': max_error if finite else None,
            'rmse_uv': float(np.sqrt(squared_error / values)) if values and finite else None,
            'values_compared': values, 'rtol': 1e-7, 'atol_uv': 1e-6}


def export_csv_bundle(raw, source_path, destination_dir):
    """Export four-file bundle and validate it; never overwrite existing output."""
    source_path, destination_dir = Path(source_path), Path(destination_dir)
    types = raw.get_channel_types()
    if not types or any(kind != 'eeg' for kind in types):
        raise ValueError('CSV bundle export requires EEG-only channels.')
    if not destination_dir.is_dir():
        raise ValueError('Output folder does not exist.')
    folder = destination_dir / f'{source_path.stem}_converted'
    if folder.exists():
        raise FileExistsError(f'Output package already exists: {folder}. Choose a new output folder.')
    folder.mkdir()
    prefix = source_path.stem
    names = [f'{prefix}_{name}' for name in ('signals.csv', 'events.csv', 'metadata.json', 'validation.json')]
    signals_path, events_path, metadata_path, validation_path = (folder/name for name in names)
    try:
        raw.load_data()
        pd.DataFrame(raw.get_data().T * 1e6, columns=raw.ch_names).to_csv(
            signals_path, index=False, float_format='%.17g')
        ann = raw.annotations
        pd.DataFrame({'onset_sec': list(map(float, ann.onset)),
                      'duration_sec': list(map(float, ann.duration)),
                      'description': list(map(str, ann.description))}).to_csv(events_path, index=False)
        locs = {}
        for ch in raw.info['chs']:
            coords = np.asarray(ch['loc'][:3], dtype=float)
            locs[ch['ch_name']] = [float(x) if np.isfinite(x) else None for x in coords]
        meta = {
            'bundle_schema': 'neuro-eeg-csv-bundle-v0.3.4',
            'source_filename': source_path.name,
            'source_format': source_path.suffix.lower(),
            'channel_names': list(raw.ch_names),
            'channel_types': dict(Counter(types)),
            'individual_channel_types': dict(zip(raw.ch_names, types)),
            'sampling_rate_hz': float(raw.info['sfreq']),
            'n_samples': int(raw.n_times), 'n_channels': len(raw.ch_names),
            'first_sample_index': int(raw.first_samp),
            'signal_units': 'microvolt',
            'time_axis': 'sample_index / sampling_rate_hz, relative to first exported sample',
            'measurement_date': _json_safe(raw.info.get('meas_date')),
            'highpass_hz': _json_safe(raw.info.get('highpass')),
            'lowpass_hz': _json_safe(raw.info.get('lowpass')),
            'description': _json_safe(raw.info.get('description')),
            'channel_locations_head_m': locs,
            'annotations_orig_time': _json_safe(ann.orig_time),
            'annotation_onsets': 'MNE Raw.annotations.onset seconds; interpret with annotations_orig_time and first_sample_index',
            'preservation_notes': [
                'CSV alone cannot represent every FIF field or measurement geometry.',
                'The JSON sidecar stores selected fields, not every internal MNE object.',
                'Stim-channel event reconstruction is not implemented.',
                'Numerical comparison checks exported signal values, not full file-format equivalence.',
            ],
        }
        metadata_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False, allow_nan=False), encoding='utf-8')
        signals = _check_signals(raw, signals_path)
        events = _check_events(raw, events_path)
        metadata = _check_metadata(raw, metadata_path)
        signals_pass = bool(signals['channel_order_match'] and signals['samples_match'] and
                            signals['all_values_finite'] and signals['all_values_close'])
        events_pass = all(v for k, v in events.items() if k.endswith('_match'))
        metadata_pass = all(metadata.values())
        report = {
            'version': '0.3.4', 'timestamp_utc': datetime.now(timezone.utc).isoformat(),
            'source': source_path.name, 'output_folder': folder.name, 'files': names,
            'signal_validation': signals, 'annotation_validation': events,
            'metadata_validation': metadata,
            'numerical_validation_passed': signals_pass,
            'annotation_validation_passed': bool(events_pass),
            'core_metadata_validation_passed': bool(metadata_pass),
            'structural_validation_passed': bool(signals['channel_order_match'] and signals['samples_match'] and metadata_pass),
            'overall_validation_passed': bool(signals_pass and events_pass and metadata_pass),
            'full_metadata_equivalence': 'NOT_VERIFIED',
            'stim_channel_event_reconstruction': 'NOT_IMPLEMENTED',
            'limitations': 'PASS applies to the listed checks only; does not establish complete format equivalence.',
        }
        report = _json_safe(report)
        validation_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False), encoding='utf-8')
        return folder, report
    except Exception:
        shutil.rmtree(folder, ignore_errors=True)
        raise
