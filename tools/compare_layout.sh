. mn_scripts/pyenv.sh

python mn_scripts/layout/layout_handler.py -i "layout/layout.yaml" -z "conf/zuul_conf/zuul.conf" merge -o "layout.yaml"
chmod 777 layout.yaml
line1=$(cat layout.yaml |head -3 |tail -1)
line2=$(cat /var/fpwork/zuul_prod/etc/layout.yaml |head -3 |tail -1)
if [ "l$line1" == "l$line2" ];then
    echo "same content layout.yaml"
    exit1
else
    cp -f layout.yaml /var/fpwork/zuul_prod/etc/layout.yaml
    echo "layout.yaml is different, updated!"
fi
sudo docker exec zuul-server bash -c 'kill -SIGHUP `supervisorctl pid zuul-server`'