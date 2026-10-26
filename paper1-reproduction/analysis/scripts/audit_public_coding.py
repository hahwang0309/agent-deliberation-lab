"""Check released coder/judge merges and count summaries, without model calls."""
import argparse
import csv
import json
from collections import Counter
from pathlib import Path


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data', required=True, type=Path)
    p.add_argument('--out', required=True, type=Path)
    a = p.parse_args()
    results = {}
    expected = {'utterance': 2440, 'device': 1500, 'evidence': 600}
    for kind, size in expected.items():
        pairs = json.loads((a.data/f'{kind}-initial-pairs.json').read_text())
        judges = {r['id']: r['labels'] for r in map(json.loads, (a.data/f'{kind}-judge.jsonl').read_text().splitlines())}
        with (a.data/f'{kind}-combined.csv').open() as f:
            rows = list(csv.DictReader(f))
        summary = json.loads((a.data/f'{kind}-summary.json').read_text())
        if len(rows) != size or len({r['id'] for r in rows}) != size:
            raise ValueError(f'Unexpected size or duplicate IDs: {kind}')
        if set(pairs) != {r['id'] for r in rows}:
            raise ValueError(f'Pair/combined ID mismatch: {kind}')
        agreement = disagreement = 0
        for r in rows:
            pair = pairs[r['id']]
            if pair['first'] == pair['second']:
                labels = pair['first']; agreement += 1
            else:
                labels = judges[r['id']]; disagreement += 1
            if any(r[field] != value for field, value in labels.items()):
                raise ValueError(f'Merge mismatch: {kind}/{r["id"]}')
        if agreement != summary['agreement_n'] or disagreement != summary['disagreement_n']:
            raise ValueError(f'Route count mismatch: {kind}')
        for condition, archived in summary['by_condition'].items():
            subset = [r for r in rows if r['label'] == condition]
            if len(subset) != archived['n']:
                raise ValueError(f'Condition size mismatch: {kind}/{condition}')
            for field, counts in archived.items():
                if field != 'n' and dict(Counter(r[field] for r in subset)) != counts:
                    raise ValueError(f'Label count mismatch: {kind}/{condition}/{field}')
        results[kind] = {'n': size, 'agreement_n': agreement, 'disagreement_n': disagreement,
                         'merged_labels_match': True, 'condition_counts_match': True}
    report = {'api_calls': 0, 'human_validation': False, 'checks': results}
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
