mail_object = {'Integration {topic} switch to {mode}': [
    {"General Information": [
        ('Integration Name', '{topic}'),
        ('Baseline package', '{base_package}'),
        ('Release Date', '[function]get_date_time')]},
    {'Rebase Result': '{rebase_result}'},
    {'How to rebase': '[link]https://confluence.ext.net.nokia.com/display/BTSSCMHGH/06+How+to+rebase+gerrit+change'},
    {'5G HZ SCM Contact': [('I_5G_CB_SCM_GMS', '[mail]I_5G_CB_SCM@internal.nsn.com')]}]}

mandatory_params = ['topic', 'base_package']
