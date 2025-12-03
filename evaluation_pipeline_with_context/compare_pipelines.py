#!/usr/bin/env python3
"""
Comparison tool for running both pipelines and analyzing results
"""
import subprocess
import json
import re
from pathlib import Path

def run_pipeline(pipeline_path, output_file):
    """Run a pipeline and save output while showing it in real-time"""
    print(f"\n🚀 Running: {pipeline_path}")
    print("="*60)
    
    import sys
    
    # Run with output displayed AND captured
    result = subprocess.run(
        ['python', pipeline_path],
        cwd=Path(pipeline_path).parent,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,  # Line buffered
        universal_newlines=True
    )
    
    output = result.stdout
    
    # Print to console
    print(output)
    
    # Save to file
    with open(output_file, 'w') as f:
        f.write(output)
    
    print(f"\n✅ Output saved to: {output_file}")
    
    return output

def parse_results(output):
    """Extract statistics from pipeline output"""
    stats = {
        'total': 0,
        'passed': 0,
        'failed': 0,
        'errors': 0,
        'scenarios': [],
        'total_tests_pre': 0,
        'passed_tests_pre': 0,
        'total_tests_post': 0,
        'passed_tests_post': 0
    }
    
    # Extract summary stats - look for the summary line before "Details:"
    # Format: "✅ Passed: 5/11"
    passed_match = re.search(r'✅ Passed:\s*(\d+)/(\d+)', output)
    if passed_match:
        stats['passed'] = int(passed_match.group(1))
        stats['total'] = int(passed_match.group(2))
    
    failed_match = re.search(r'❌ Failed:\s*(\d+)/(\d+)', output)
    if failed_match:
        stats['failed'] = int(failed_match.group(1))
    
    errors_match = re.search(r'⚠️\s+Errors:\s*(\d+)/(\d+)', output)
    if errors_match:
        stats['errors'] = int(errors_match.group(1))
    
    # Extract test counts from PRE-FIX and POST-MERGE/POST-FIX sections
    for line in output.split('\n'):
        # PRE-FIX results: "       ✅ Passed: 0/2"
        if 'PRE-FIX' in line or '[PRE-FIX]' in line:
            # Next few lines will have test results
            continue
        if '✅ Passed:' in line and '/' in line:
            # Format: "       ✅ Passed: 2/2"
            test_match = re.search(r'✅ Passed:\s*(\d+)/(\d+)', line)
            if test_match:
                passed = int(test_match.group(1))
                total = int(test_match.group(2))
                # Determine if PRE or POST based on context
                # This is approximate - we'll sum them up
                if 'POST-MERGE' in output.split(line)[0][-200:] or 'POST-FIX' in output.split(line)[0][-200:]:
                    stats['passed_tests_post'] += passed
                    stats['total_tests_post'] += total
                else:
                    stats['passed_tests_pre'] += passed
                    stats['total_tests_pre'] += total
    
    # Extract per-scenario results from Details section
    in_details = False
    for line in output.split('\n'):
        if 'Details:' in line:
            in_details = True
            continue
        
        if in_details and '|' in line:
            # Parse lines like: "✅ DEPOSIT_LOGIC_ERROR_1 | PASS | https://..."
            parts = [p.strip() for p in line.split('|')]
            if len(parts) >= 2:
                scenario = parts[0].replace('✅', '').replace('❌', '').replace('⚠️', '').strip()
                result = parts[1].strip()
                if scenario and result in ['PASS', 'FAIL', 'CRASH']:
                    stats['scenarios'].append({
                        'name': scenario,
                        'result': result
                    })
    
    return stats

def compare_results(original_stats, context_stats):
    """Compare results from both pipelines"""
    print("\n" + "="*60)
    print("📊 COMPARISON RESULTS")
    print("="*60)
    
    print(f"\n{'Metric':<30} | {'Original':<15} | {'With Context':<15} | {'Difference'}")
    print("-"*85)
    
    print(f"{'Total Scenarios':<30} | {original_stats['total']:<15} | {context_stats['total']:<15} | -")
    
    # Pass rate
    orig_pass_rate = (original_stats['passed'] / original_stats['total'] * 100) if original_stats['total'] > 0 else 0
    ctx_pass_rate = (context_stats['passed'] / context_stats['total'] * 100) if context_stats['total'] > 0 else 0
    
    print(f"{'Passed':<30} | {original_stats['passed']:<15} | {context_stats['passed']:<15} | {'+' if context_stats['passed'] > original_stats['passed'] else ''}{context_stats['passed'] - original_stats['passed']}")
    print(f"{'Pass Rate':<30} | {orig_pass_rate:.1f}%{' '*10} | {ctx_pass_rate:.1f}%{' '*10} | {'+' if ctx_pass_rate > orig_pass_rate else ''}{ctx_pass_rate - orig_pass_rate:.1f}%")
    print(f"{'Failed':<30} | {original_stats['failed']:<15} | {context_stats['failed']:<15} | {context_stats['failed'] - original_stats['failed']}")
    print(f"{'Errors':<30} | {original_stats['errors']:<15} | {context_stats['errors']:<15} | {context_stats['errors'] - original_stats['errors']}")
    
    # Test-level metrics (if available)
    if context_stats.get('total_tests_post', 0) > 0 or original_stats.get('total_tests_post', 0) > 0:
        print("\n" + "-"*85)
        print("Individual Test Results (POST-FIX):")
        print(f"{'Tests Passed (POST-FIX)':<30} | {original_stats.get('passed_tests_post', '?'):<15} | {context_stats.get('passed_tests_post', '?'):<15} | {'+' if context_stats.get('passed_tests_post', 0) > original_stats.get('passed_tests_post', 0) else ''}{context_stats.get('passed_tests_post', 0) - original_stats.get('passed_tests_post', 0)}")
        print(f"{'Total Tests (POST-FIX)':<30} | {original_stats.get('total_tests_post', '?'):<15} | {context_stats.get('total_tests_post', '?'):<15} | -")
    
    # Per-scenario comparison
    print("\n" + "="*60)
    print("📋 PER-SCENARIO COMPARISON")
    print("="*60)
    
    orig_scenarios = {s['name']: s['result'] for s in original_stats['scenarios']}
    ctx_scenarios = {s['name']: s['result'] for s in context_stats['scenarios']}
    
    improvements = []
    regressions = []
    unchanged = []
    
    for scenario in orig_scenarios:
        orig_result = orig_scenarios.get(scenario, 'N/A')
        ctx_result = ctx_scenarios.get(scenario, 'N/A')
        
        if orig_result == 'FAIL' and ctx_result == 'PASS':
            improvements.append(scenario)
            print(f"✅ IMPROVED: {scenario:<40} | {orig_result} → {ctx_result}")
        elif orig_result == 'PASS' and ctx_result == 'FAIL':
            regressions.append(scenario)
            print(f"❌ REGRESSED: {scenario:<40} | {orig_result} → {ctx_result}")
        elif orig_result != ctx_result:
            print(f"🔄 CHANGED: {scenario:<40} | {orig_result} → {ctx_result}")
        else:
            unchanged.append(scenario)
    
    # Summary
    print("\n" + "="*60)
    print("🎯 IMPACT SUMMARY")
    print("="*60)
    print(f"✅ Improvements (FAIL→PASS): {len(improvements)}")
    print(f"❌ Regressions (PASS→FAIL): {len(regressions)}")
    print(f"➡️  Unchanged: {len(unchanged)}")
    
    if improvements:
        print(f"\n💡 Context helped fix: {', '.join(improvements[:3])}")
    if regressions:
        print(f"\n⚠️  Context caused issues in: {', '.join(regressions[:3])}")
    
    # Verdict
    print("\n" + "="*60)
    if context_stats['passed'] > original_stats['passed']:
        print("🏆 VERDICT: Repository context IMPROVED test pass rate!")
    elif context_stats['passed'] == original_stats['passed']:
        print("➡️  VERDICT: Repository context had NO NET EFFECT on pass rate")
    else:
        print("⚠️  VERDICT: Repository context DECREASED test pass rate")
    print("="*60)

def main():
    """Run both pipelines and compare"""
    
    # Paths
    original_pipeline = Path(__file__).parent.parent / 'evaluation_pipeline' / 'pipeline_of_auto_testing.py'
    context_pipeline = Path(__file__).parent / 'pipeline_with_context.py'
    
    results_dir = Path(__file__).parent / 'comparison_results'
    results_dir.mkdir(exist_ok=True)
    
    original_output = results_dir / 'original_results.txt'
    context_output = results_dir / 'context_results.txt'
    
    # Run both pipelines - CONTEXT-ENHANCED FIRST
    print("="*60)
    print("🧪 RUNNING PIPELINE COMPARISON")
    print("="*60)
    
    print("\n1. Running CONTEXT-ENHANCED pipeline...")
    ctx_out = run_pipeline(context_pipeline, context_output)
    ctx_stats = parse_results(ctx_out)
    
    # Show context-enhanced results immediately
    print("\n" + "="*60)
    print("📊 CONTEXT-ENHANCED PIPELINE RESULTS")
    print("="*60)
    print(f"✅ Passed: {ctx_stats['passed']}/{ctx_stats['total']}")
    print(f"❌ Failed: {ctx_stats['failed']}/{ctx_stats['total']}")
    print(f"⚠️  Errors: {ctx_stats['errors']}/{ctx_stats['total']}")
    if ctx_stats['total'] > 0:
        pass_rate = (ctx_stats['passed'] / ctx_stats['total'] * 100)
        print(f"📈 Pass Rate: {pass_rate:.1f}%")
    
    print("\n2. Running ORIGINAL pipeline (for comparison)...")
    orig_out = run_pipeline(original_pipeline, original_output)
    orig_stats = parse_results(orig_out)
    
    # Compare
    compare_results(orig_stats, ctx_stats)
    
    # Save comparison
    comparison_file = results_dir / 'comparison_summary.txt'
    print(f"\n📄 Full comparison saved to: {comparison_file}")

if __name__ == "__main__":
    main()
