import fire
from mod import wft_tools


def get_rcp_vdu_info(baseline):
    gcc_path = None
    gcc_version = None
    os_version = None

    sub_builds = wft_tools.get_subuild_from_wft(baseline)

    for build in sub_builds:
        if "GNU toolchain" in build["component"]:
            gcc_path = build["version"].split("toolchain")[0]
            print("gcc path is {0}".format(gcc_path))
        if "GCCVersion" in build["component"]:
            gcc_version = build["version"]
            print("gcc version is {0}".format(gcc_version))
        if "OSVersion" in build["component"]:
            os_version = build["version"]
            print("os version is {0}".format(os_version))

    if gcc_path and gcc_version and os_version:
        return gcc_path, gcc_version + "-" + os_version
    else:
        raise Exception("Can not get GNU toolchain or GCCVersion or OSVersion from WFT, \
        please check if the sub builds in {} from WFT is correct!".format(baseline))


def create_prop_fie(baseline, gcc_version, gcc_path):
    content = "RCP_VERSION=" + str(baseline) + "\n"
    content += "gcc_version=" + str(gcc_version) + "\n"
    content += "gcc_path=" + str(gcc_path)

    with open("gcc_param.prop", "w") as f:
        f.write(content)

    with open("vdu_param.prop", "w") as vdu_f:
        vdu_f.write("RCP_VERSION={0}".format(str(baseline).split("_")[1]))


def main(baseline):
    gcc_path, gcc_version = get_rcp_vdu_info(baseline)
    create_prop_fie(baseline, gcc_version, gcc_path)


if __name__ == '__main__':
    fire.Fire(main)
