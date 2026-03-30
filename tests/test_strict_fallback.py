from backend.agents.coding_logic import CodingLogicAgent

# EXACT TEST: This is where it was failing
note = '''Patient has Type 2 diabetes mellitus with peripheral neuropathy,
chronic kidney disease stage 3, obesity, hyperlipidemia,
acute systolic heart failure, and underwent laparoscopic cholecystectomy.'''

agent = CodingLogicAgent()
result = agent.run_sync(note)

print('=== CRITICAL BUG TEST ===')
print('Input: diabetes, CKD, HF, obesity, hyperlipidemia')
print()
print('Final codes:')
codes = result['data']['codes']
for c in codes:
    code = c['code']
    desc = c['description']
    print(code + ' - ' + desc)

print()
print('=== VALIDATION ===')
codes_set = {c['code'] for c in codes}

# Check for false positives
false_positives = []
if 'I21.9' in codes_set:
    false_positives.append('I21.9 (myocardial infarction - FALSE POSITIVE)')
if 'G62.9' in codes_set and 'E11.42' in codes_set:
    false_positives.append('G62.9 (duplicate neuropathy when E11.42 covers it)')

if false_positives:
    print('STILL HAS BUGS:')
    for fp in false_positives:
        print('  - ' + fp)
else:
    print('SUCCESS! ALL CRITICAL BUGS FIXED!')
    print('✓ No false positives (I21.9 correctly excluded)')
    print('✓ No duplicate coding (G62.9 correctly excluded)')
