import yaml
from mod import config_yaml


def parse_env_change_split(env_change_split):
    env_change_dict = {}
    for env_line in env_change_split:
        if '=' in env_line:
            key, value = env_line.split('=', 1)
            env_change_dict[key.strip()] = value.strip()
    return env_change_dict


def create_config_yaml_by_env_change(env_change_split, rest,
                                     change_id, config_yaml_file='config.yaml'):
    change_content = rest.get_file_change(config_yaml_file, change_id)
    old_content = change_content['old']
    if not old_content:
        try:
            print('get content from {} in {}'.format(config_yaml_file, change_id))
            old_content = rest.get_file_content(config_yaml_file, change_id)
        except Exception:
            print('Cannot find {} in {}'.format(config_yaml_file, change_id))
    if not old_content:
        return {}
    config_yaml_obj = config_yaml.ConfigYaml(config_yaml_content=old_content)
    # update env_change in config.yaml
    # update staged infos if exists
    config_yaml_obj.update_by_env_change(parse_env_change_split(env_change_split))
    config_yaml_content = yaml.safe_dump(config_yaml_obj.config_yaml, default_flow_style=False)
    if config_yaml_content != old_content:
        return {config_yaml_file: config_yaml_content}
    return {}


def create_config_yaml_by_content_change(rest, old_content, new_content,
                                         change_no, config_yaml_file='config.yaml'):
    old_config_yaml = config_yaml.ConfigYaml(config_yaml_content=old_content)
    new_config_yaml = config_yaml.ConfigYaml(config_yaml_content=new_content)
    file_content = rest.get_file_content(config_yaml_file, change_no)
    final_config_yaml = config_yaml.ConfigYaml(config_yaml_content=file_content)
    for new_key, section in new_config_yaml.components.items():
        if new_key in final_config_yaml.components:
            print('update section {}'.format(new_key))
            final_config_yaml.components[new_key].update(section)
        else:
            print('add section {}'.format(new_key))
            final_config_yaml.components[new_key] = section
    for old_key, section in old_config_yaml.components.items():
        if old_key not in new_config_yaml.components:
            print('remove section key {}'.format(old_key))
            final_config_yaml.components.pop(old_key)
    config_yaml_content = yaml.safe_dump(final_config_yaml.config_yaml, default_flow_style=False)
    if config_yaml_content != file_content:
        return {config_yaml_file: config_yaml_content}
    return {}


def create_file_change_by_env_change(env_change_split, file_content, filename):
    lines = file_content.split('\n')
    change_dict = parse_env_change_split(env_change_split)
    for i, line in enumerate(lines):
        if '=' in line:
            key2, value2 = line.strip().split('=', 1)
            if key2.strip() in change_dict:
                lines[i] = key2 + '=' + change_dict[key2.strip()]
    for env_line in env_change_split:
        if env_line.startswith('#'):
            lines.append(env_line)
    ret_dict = {filename: '\n'.join(lines)}
    return ret_dict
