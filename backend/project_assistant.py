"""Useful project guidance without pretending a model or command ran."""

def local_guidance(message: str, context: dict, report: dict | None = None) -> str:
    question = message.lower()
    details = context.get('details', {})
    overview = context['context_summary']
    if details.get('java_target'):
        overview += f"\nConfigured Java target: {details['java_target']}. Artifact: {details.get('artifact', 'unknown')}."
    if details.get('route_hints'):
        overview += '\nPaths found in application source: ' + ', '.join(details['route_hints']) + '.'
    if any(word in question for word in ('coverage', 'report', 'risk', 'result')):
        if not report:
            return overview + '\n\nNo verification report is available yet. Importing source files does not execute migration checks. Start a verification run to collect baseline/migrated builds, tests and coverage.'
        verdict = report.get('verdict', {})
        lines = [overview, '', 'Stored verdict: ' + str(verdict.get('value', 'INCONCLUSIVE'))]
        for variant in ('baseline', 'migrated'):
            tests = report.get('tests', {}).get(variant, [])
            lines.append(f'{variant}: {sum(test["status"] == "pass" for test in tests)}/{len(tests)} recorded tests passed.')
            coverage = report.get('coverage', {}).get(variant) or {}
            ratio = coverage.get('counters', {}).get('line', {}).get('ratio')
            lines.append(f'Line coverage: {ratio:.1%}.' if coverage.get('measured') and ratio is not None else 'Line coverage: unavailable.')
        lines.extend(reason['message'] for reason in verdict.get('reasons', []))
        lines.append('Passing checks do not prove behavioral equivalence. This summary uses stored evidence only.')
        return '\n'.join(lines)
    if any(word in question for word in ('migrat', 'upgrade', 'java 17')):
        return overview + '\n\nSuggested Java 8 → 17 plan (no edits or commands executed):\n1. Preserve the original commit and run the baseline tests on Java 8.\n2. Update the Maven compiler target in a separate working copy. Keep javax.servlet unless the chosen servlet stack requires a namespace migration.\n3. Run the same tests on Java 17 and compare test identities, assertions, bytecode and measured coverage.\n4. Review the diff and evidence before approval. Missing required build or test evidence remains inconclusive; unavailable coverage requires review.'
    if any(word in question for word in ('run', 'start', 'preview', 'command')):
        return overview + '\n\nUse Preview to view a configured running application. To run this Maven project locally, open its folder and use the Maven Wrapper described in README.md (Windows: .\\mvnw.cmd clean package). Start its executable JAR using the README instructions. The workspace terminal runs commands only when an isolated execution host is enabled. Chat never silently executes commands.'
    return overview + '\n\nAsk: “Plan the Java 8 to Java 17 migration”, “How do I run this project?”, or “Summarize the verification results and coverage”. This is local project analysis; no external AI model was called.'
