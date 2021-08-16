
rm -rf zuul_urls.txt
cat id.txt | xargs -I '%%' bash __zuul-exec-command-in-k8s.sh '%%' zuul-merger "grep zuul_url /etc/zuul/zuul.conf" >> zuul_urls.txt
