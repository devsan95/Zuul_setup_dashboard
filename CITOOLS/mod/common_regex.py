import re


int_firstline_reg = re.compile(r'<(.*?)>\s+on\s+<(.*?)>\s+of\s+<(.*?)>\s+topic\s+<(.*?)>', re.DOTALL)
gnb_firstline_reg = re.compile(r'(\[.*\])\s+(([a-zA-Z0-9\.\-_]+)\s+){1,2}([a-zA-Z0-9\.\-_]+)\s+([a-zA-Z0-9\.\-_\/]+)', re.DOTALL)
jira_title_reg = re.compile(r'(([a-zA-Z0-9\.\-_]+)\s+){3}(([a-zA-Z0-9\.\-_\/]+)-([a-zA-Z0-9\.\-_\/]+))\s+([a-zA-Z0-9\.\-_]+)')
COMP_VERSION_REGEX = [r'-[a-z0-9]{24,}', r'-[0-9\.\-_]+', r'-[a-zA-Z0-9\.\-_]+', '']
fifi_reg = re.compile(r'%FIFI=(.*)')
