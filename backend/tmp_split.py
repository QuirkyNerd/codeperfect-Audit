import sys

with open('d:/Desktop/adi1/virtusa_jatayu/CodePerfectAuditor/backend/services/clinical_rules_config.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

def extract_block(var_name):
    start_idx = -1
    for i, line in enumerate(lines):
        if line.startswith(var_name + ':') or line.startswith(var_name + ' =') or line.startswith('def ' + var_name):
            start_idx = i
            break
    if start_idx == -1: return ''
    
    content = []
    level = 0
    in_str = False
    escape = False
    str_char = ''
    
    for line in lines[start_idx:]:
        content.append(line)
        for char in line:
            if escape:
                escape = False
                continue
            if char == '\\':
                escape = True
                continue
            if in_str:
                if char == str_char:
                    in_str = False
            else:
                if char in ('\'', '"'):
                    in_str = True
                    str_char = char
                elif char in ('{', '[', '('):
                    level += 1
                elif char in ('}', ']', ')'):
                    level -= 1
        
        if line.startswith('def '):
            level = -999
            
        if level <= 0:
            if level == -999 and line.strip() == '' and len(content) > 3:
                break
            if level == 0 and not line.startswith('def '):
                break
                
    return ''.join(content)

with open('d:/Desktop/adi1/virtusa_jatayu/CodePerfectAuditor/backend/services/group_config.py', 'w', encoding='utf-8') as f:
    f.write("# services/group_config.py\n\n")
    f.write(extract_block('MANDATORY_GROUPS') + "\n\n")
    f.write(extract_block('CKD_ENTITY_SIGNALS') + "\n\n")
    f.write(extract_block('ENTITY_PREFIX_MAP') + "\n")

with open('d:/Desktop/adi1/virtusa_jatayu/CodePerfectAuditor/backend/services/validation_rules.py', 'w', encoding='utf-8') as f:
    f.write("# services/validation_rules.py\nimport re as _re\n\n")
    f.write(extract_block('clean_rag_description') + "\n\n")
    f.write(extract_block('CLINICAL_EXCLUSIVITY_RULES') + "\n\n")
    f.write(extract_block('HARD_REJECT_PREFIXES') + "\n\n")
    f.write(extract_block('ALWAYS_REJECT_PREFIXES') + "\n\n")
    f.write(extract_block('RENAL_SYNDROME_PREFIXES') + "\n\n")
    f.write(extract_block('RELATIONSHIP_VALIDATION_RULES') + "\n")

with open('d:/Desktop/adi1/virtusa_jatayu/CodePerfectAuditor/backend/services/compound_rules.py', 'w', encoding='utf-8') as f:
    f.write("# services/compound_rules.py\n\n")
    f.write(extract_block('COMPOUND_RULES') + "\n")

print("Done")
