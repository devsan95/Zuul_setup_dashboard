import re


int_firstline_reg = re.compile(r'<(.*?)>\s+on\s+<(.*?)>\s+of\s+<(.*?)>\s+topic\s+<(.*?)>', re.DOTALL)
COMP_VERSION_REGEX = [r'-[a-z0-9]{24,}', r'-[0-9\.\-_]+', r'-[a-zA-Z0-9\.\-_]+', '']
fifi_reg = re.compile(r'%FIFI=(.*)')
