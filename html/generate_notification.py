import click
import cgi
import arrow
from api import gerrit_rest
import codecs


@click.command()
@click.option('--title', required=True)
@click.option('--content', required=True)
@click.option('--author', required=True)
@click.option('--alert-type', type=click.Choice(['success', 'info', 'warning', 'danger']), default='info')
@click.option('--icon', default='glyphicon-info-sign')
@click.option('--label', default=None)
@click.option('--label-type', type=click.Choice(['default', 'primary', 'success', 'info', 'warning', 'danger']), default='default')
@click.option('--gerrit-path', default=None)
@click.option('--project', default=None)
@click.option('--branch', default=None)
@click.option('--file-path', default=None)
def main(title, content, author, alert_type, icon, label, label_type, gerrit_path, project, branch, file_path):
    title = codecs.decode(cgi.escape(title), 'utf-8')
    content = codecs.decode(cgi.escape(content), 'utf-8')
    author = codecs.decode(cgi.escape(author), 'utf-8')
    alert_type = cgi.escape(alert_type)
    icon = cgi.escape(icon)
    label = codecs.decode(cgi.escape(label), 'utf-8')
    label_type = cgi.escape(label_type)
    template = """
<div class="alert alert-{alert_type}" role="alert">
        <div style="display: flex;flex-direction: row;">
                <div class="col-1 alert-icon-col" style="float:left;margin-right:10px;">
                    <span class="glyphicon {icon}"></span>
                </div>
                <div class="col">
                        <h4 class="alert-heading">{title} {label}</h4>
                        <p>{content}</p>
                        <p style="margin-top:15px;margin-bottom:-5px"><span class="glyphicon glyphicon-user"></span> {author} <span> </span><span class="glyphicon glyphicon-time"></span> <span id="notification_date"></span><script>var update_time = new Date({time}); $('#notification_date').html(update_time.toString());</script> </p>
                </div>
        </div>
</div>
    """
    if title:
        content_line = '<br />'.join(content.split('\n'))
        label_template = '<span class="label label-{type}">{label}</span>'
        label_line = ''
        if label:
            label_line = label_template.format(type=label_type, label=label)

        time_now = arrow.utcnow()

        output = template.format(alert_type=alert_type, icon=icon, title=title,
                                 label=label_line, content=content_line,
                                 author=author, time=time_now.timestamp * 1000)
    else:
        output = ""

    if gerrit_path:
        rest = gerrit_rest.init_from_yaml(gerrit_path)
        change_id, ticket_id, rest_id = rest.create_ticket(project, None, branch, 'Update Notification')
        try:
            rest.add_file_to_change(rest_id, file_path, output)
            rest.publish_edit(rest_id)
            rest.review_ticket(rest_id, 'Try to merge', {'Code-Review': 2, 'Verified': 1, 'Gatekeeper': 1})
            rest.submit_change(rest_id)
        except Exception as e:
            rest.abandon_change(rest_id)
            raise e


if __name__ == '__main__':
    main()
