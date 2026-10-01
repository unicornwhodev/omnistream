-- Stage the Python bridge through the Kit App Template extension build.
local extension = get_current_extension_info()
project_ext(extension)
repo_build.prebuild_link {
    { "omnistream", extension.target_dir .. "/omnistream" },
}
