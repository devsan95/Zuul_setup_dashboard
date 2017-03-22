import os
import urllib
import urllib2


def downloadPage(url, dst=None):
    if not dst:
        file_name = url.split('/')[-1]
        dst = os.path.join(os.getcwd(), file_name)
    print "download: %s" % url
    u = urllib.urlopen(url, dst)
    with open(file_name, 'wb') as f:
        meta = u.info()
        print meta
        heads = meta.getheaders("Content-Length")
        if heads:
            file_size = int(meta.getheaders("Content-Length")[0])
            print "Downloading: %s Bytes: %s" % (file_name, file_size)

            file_size_dl = 0
            block_sz = 8192
            while True:
                buffer = u.read(block_sz)
                if not buffer:
                    break
                file_size_dl += len(buffer)
                f.write(buffer)
                status = r"%10d  [%3.2f%%]" % (
                    file_size_dl, file_size_dl * 100. / file_size)
                status = status + chr(8) * (len(status) + 1)
                print status


def download(url, dst=None):
    """
    a function to download file from url
    """
    if not dst:
        file_name = url.split('/')[-1]
        dst = os.path.join(os.getcwd(), file_name)
    print "download: %s" % url
    file_name, heads = urllib.urlretrieve(url, dst)


def httpfetch(url, timeout=30, logger=None):
    if logger:
        logger.info("httpFetch: %s" % url)
    else:
        print ("httpFetch: %s" % url)

    u = urllib2.urlopen(url, None, timeout)

    meta = u.info()
    heads = meta.getheaders("Content-Length")
    file_size = 0
    if heads:
        file_size = int(meta.getheaders("Content-Length")[0])
        if logger:
            logger.info("Response Size: %s" % file_size)
        else:
            print "Response Size: %s" % file_size

    file_size_dl = 0
    block_sz = 8192
    content = ''
    while True:
        buffer = u.read(block_sz)
        if not buffer or len(buffer) == 0:
            break
        content += buffer
        file_size_dl += len(buffer)

        if file_size > 0:
            status = r"%10d  [%3.2f%%]" % (
                file_size_dl, file_size_dl * 100. / file_size)
            status = status + chr(8) * (len(status) + 1)
        else:
            status = r"%10d  [??%%]" % (file_size_dl)
            status = status + chr(8) * (len(status) + 1)

        if logger:
            logger.info(status)
        else:
            print status

    return content
