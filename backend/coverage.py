"""Read observed JaCoCo XML counters; unavailable data never becomes 100%."""
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET

def collect_coverage(working: Path, destination: Path, expected_classes: dict[str, set[str]]) -> dict | None:
    modules = {}
    for path in working.rglob('jacoco.xml'):
        if not path.resolve().is_relative_to(working) or path.parts[-4:-1] != ('target', 'site', 'jacoco'):
            continue
        try:
            root = ET.parse(path).getroot()
            if root.tag != 'report' or not root.findall('sessioninfo'):
                continue
            counters = {}
            for counter in root.findall('counter'):
                covered, missed = int(counter.attrib['covered']), int(counter.attrib['missed'])
                if min(covered, missed) < 0:
                    raise ValueError('Negative coverage counter')
                total = covered + missed
                counters[counter.attrib['type'].lower()] = {'covered': covered, 'missed': missed, 'total': total, 'ratio': covered / total if total else None}
            if not counters.get('instruction', {}).get('total') or not counters.get('line', {}).get('total'):
                continue
            module = path.parents[3].relative_to(working).as_posix()
            names = {item.attrib['name'] for item in root.findall('./package/class')}
            missing = sorted(expected_classes.get(module, set()) - names)
            target = destination / module / 'coverage'
            target.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target / 'jacoco.xml')
            modules[module] = {'counters': counters, 'missing_classes': missing, 'report': str(target / 'jacoco.xml')}
        except (ET.ParseError, OSError, KeyError, ValueError):
            continue
    if not modules:
        return None
    # Modules with bytecode but no coverage report must remain visible.
    missing_modules = sorted(set(expected_classes) - set(modules))
    totals = {}
    for module in modules.values():
        for name, counter in module['counters'].items():
            total = totals.setdefault(name, {'covered': 0, 'missed': 0})
            total['covered'] += counter['covered']
            total['missed'] += counter['missed']
    for counter in totals.values():
        counter['total'] = counter['covered'] + counter['missed']
        counter['ratio'] = counter['covered'] / counter['total'] if counter['total'] else None
    return {'measured': True, 'tool': 'JaCoCo', 'modules': modules, 'counters': totals, 'missing_modules': missing_modules}

def coverage_changes(baseline: dict | None, migrated: dict | None) -> list[dict]:
    if not baseline or not migrated:
        return []
    changes = []
    for module, before in baseline.get('modules', {}).items():
        after = migrated.get('modules', {}).get(module)
        if not after:
            changes.append({'module': module, 'metric': 'scope', 'message': f'Coverage report for module {module} is missing after migration.'})
            continue
        for metric in ('line', 'branch'):
            old = before['counters'].get(metric, {}).get('ratio')
            new = after['counters'].get(metric, {}).get('ratio')
            if old is not None and (new is None or new + 1e-12 < old):
                changes.append({'module': module, 'metric': metric, 'baseline': old, 'migrated': new, 'message': f'{metric.capitalize()} coverage decreased in module {module}; review whether the change is legitimate.'})
    return changes
