


while read id; do
	_id=$(echo $id|xargs echo -n)
	echo $_id
	sh zuul-exec-cmd-in-container.sh $_id "mysql" 

done < ids.txt
