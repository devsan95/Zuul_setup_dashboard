python () {
    src_uri = d.getVar("SRC_URI", True)
    src_uri = src_uri.replace("gitsm://", "git://")
    d.setVar("SRC_URI", src_uri)
}
