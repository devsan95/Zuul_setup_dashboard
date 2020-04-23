import fire
from api import gerrit_rest, mysql_api


def get_open_topics(mysql):
    sql = "SELECT issue_key FROM t_issue WHERE `status` = 'Open'"
    return [issue[0] for issue in mysql.executor(sql=sql, output=True)]


def comment_changes(issue_key, mysql, gerrit, dry_run):
    print("%s :" % issue_key)
    sql = "SELECT `change` FROM t_commit_component WHERE issue_key='{0}'".format(issue_key)
    for change in mysql.executor(sql=sql, output=True):
        if dry_run:
            print("INFO: Dry run mode: Comment in {0}".format(change[0]))
            continue
        print("INFO: Commenting in {0}".format(change[0]))
        try:
            gerrit.review_ticket(change[0], "Robot Comment: Keep change active")
        except Exception:
            print('WARNING: Failed to comment in {0}'.format(change[0]))


def run(mysql_yaml, gerrit_yaml, dry_run=True):
    mysql = mysql_api.init_from_yaml(mysql_yaml, 'skytrack')
    mysql.init_database('skytrack')
    gerrit = gerrit_rest.init_from_yaml(gerrit_yaml)
    print(get_open_topics(mysql))
    for issue_key in get_open_topics(mysql):
        comment_changes(issue_key, mysql, gerrit, dry_run=dry_run)


if __name__ == '__main__':
    fire.Fire(run)
