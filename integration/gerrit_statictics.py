import fire
import xlwt
import datetime

from api import gerrit_rest


def get_gerrit_changes(rest, project, start, end, status=None, branch='master'):
    query_str = 'project:{project} branch:{branch} status:{status} after:{start} before:{end}'.format(
        project=project,
        branch=branch,
        status=status,
        start=start,
        end=end
    ) if status else 'project:{project} branch:{branch} after:{start} before:{end}'.format(
        project=project,
        branch=branch,
        start=start,
        end=end
    )
    print query_str
    result = rest.query_ticket(query_str)
    return result


def filter_gerrit_info(detailed_info):
    status = detailed_info['status']
    submitted = detailed_info['submitted'] if detailed_info['status'] == 'MERGED' else ''
    closed = ''
    if status == 'MERGED':
        closed = submitted
    elif status == 'ABANDONED':
        for message in detailed_info['messages']:
            if message['message'] == 'Abandoned':
                closed = message['date']
    else:
        closed = ' '
    return {
        'status': status,
        'owner': detailed_info['owner']['name'],
        'created': detailed_info['created'],
        'submitted': submitted,
        'closed': closed
    }


def write_to_xls(worksheet, line, change_id, change_info):
    worksheet.write(line, 0, label='{0}'.format(change_id))
    worksheet.write(line, 1, label='{0}'.format(change_info['owner']))
    worksheet.write(line, 2, label='{0}'.format(change_info['status']))
    worksheet.write(line, 3, label='{0}'.format(change_info['created']))
    worksheet.write(line, 4, label='{0}'.format(change_info['submitted']))
    worksheet.write(line, 5, label='{0}'.format(change_info['closed']))


def run(gerrit_info_path, project, start, end=None, status=None, branch='master'):
    end = str(datetime.datetime.now()).split()[0] if not end else end
    rest = gerrit_rest.init_from_yaml(gerrit_info_path)
    gerrit_changes = get_gerrit_changes(rest, project, status=status, start=start, end=end, branch=branch)
    workbook = xlwt.Workbook(encoding='ascii')
    worksheet = workbook.add_sheet('GNB')
    worksheet.write(0, 0, label='Change ID')
    worksheet.write(0, 1, label='Owner')
    worksheet.write(0, 2, label='Status')
    worksheet.write(0, 3, label='Created')
    worksheet.write(0, 4, label='Submitted')
    worksheet.write(0, 5, label='Closed')
    line = 0
    for change in gerrit_changes:
        line += 1
        change_info = filter_gerrit_info(rest.get_detailed_ticket(change['_number']))
        write_to_xls(worksheet, line, change['_number'], change_info)
    book_name = '{name}.xls'.format(
        name=start + '-' + end
    )
    workbook.save(book_name)


if __name__ == '__main__':
    fire.Fire(run)
