ECL_YAML_MAP = {
    "ECL_GLOBAL_ENV": "Common:GLOBAL_ENV",
    "ECL_PS_REL": "PS:PS",
    "ECL_COMMON_APPL_ENV": "Common:COMMON_APPL_ENV",
    "ECL_SACK_BASE": "Common:ECL_SACK_BASE"
}

ECL_ENV_MAP = {
    "ECL_GLOBAL_ENV": "ENV_GLOBAL_ENVV",
    "ECL_PS_REL": "ENV_PS_REL",
    "ECL_COMMON_APPL_ENV": "ENV_COMMON_APPL_ENV",
    "ECL_SACK_BASE": "ENV_SBTS_ECL_SACK_BASE"
}


def create_ecl_file_change_by_env_change_dict(change_dict, file_content, filename):
    lines = file_content.split('\n')
    for i, line in enumerate(lines):
        if '=' in line:
            key, value = line.strip().split('=', 1)
            print('try to find key {} in ECL'.format(key))
            if key.strip() in ECL_YAML_MAP.keys():
                if ECL_YAML_MAP[key.strip()] in change_dict:
                    print('find key {}'.format(key))
                    lines[i] = key.strip() + '=' + change_dict[ECL_YAML_MAP[key.strip()].strip()]
                if ECL_ENV_MAP[key.strip()] in change_dict:
                    print('find key {}'.format(key))
                    print change_dict[ECL_ENV_MAP[key.strip()].strip()]
                    lines[i] = key.strip() + '=' + change_dict[ECL_ENV_MAP[key.strip()].strip()]
    ret_dict = {filename: '\n'.join(lines)}
    return ret_dict
