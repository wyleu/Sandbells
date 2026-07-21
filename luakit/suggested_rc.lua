------------------------------------------------------------------------------
-- luakit configuration file (Sandbells kiosk edition)
-- Forces fullscreen, keeps UI minimal for non-technical users
------------------------------------------------------------------------------

require "lfs"

-- Check for lua configuration files that will never be loaded because they are
-- shadowed by builtin modules.
table.insert(package.loaders, 2, function (modname)
    if not package.searchpath then return end
    local f = package.searchpath(modname, package.path)
    if not f or f:find(luakit.install_paths.install_dir .. "/", 0, true) ~= 1 then
        return
    end
    local lf = luakit.config_dir .. "/" .. modname:gsub("%.","/") .. ".lua"
    if f == lf then
        msg.warn("Loading local version of '" .. modname .. "' module: " .. lf)
    elseif lfs.attributes(lf) then
        msg.warn("Found local version " .. lf
            .. " for core module '" .. modname
            .. "', but it won't be used, unless you update 'package.path' accordingly.")
    end
end)

require "unique_instance"

-- Keep process count modest on Pi 3
luakit.process_limit = 2
soup.cookies_storage = luakit.data_dir .. "/cookies.db"

local lousy = require "lousy"
lousy.theme.init(lousy.util.find_config("theme.lua"))
assert(lousy.theme.get(), "failed to load theme")

-- ------------------------------------------------------------------
-- FULLSCREEN – the single most important line for the kiosk
-- ------------------------------------------------------------------
local window = require "window"
window.add_signal("init", function(w)
    w.win.fullscreen = true
    -- Optional: remove the status bar completely for ultra-clean look
    -- w.sbar.ebox:hide()
end)

local webview = require "webview"
local log_chrome = require "log_chrome"

window.add_signal("build", function (w)
    local widgets, l, r = require "lousy.widget", w.sbar.l, w.sbar.r
    -- Keep a very minimal status bar (or comment these out to hide entirely)
    l.layout:pack(widgets.uri())
    l.layout:pack(widgets.progress())
    r.layout:pack(widgets.buf())
    r.layout:pack(widgets.ssl())
end)

local modes = require "modes"
local binds = require "binds"
local settings = require "settings"
require "settings_chrome"

----------------------------------
-- Optional user script loading --
----------------------------------
-- Keep only what is needed; every extra module costs RAM on a Pi 3
local adblock = require "adblock"
-- local adblock_chrome = require "adblock_chrome"
-- local webinspector = require "webinspector"
-- local formfiller = require "formfiller"
-- local proxy = require "proxy"
-- local quickmarks = require "quickmarks"
local session = require "session"
-- local undoclose = require "undoclose"
-- local tabhistory = require "tabhistory"
-- local userscripts = require "userscripts"
-- local bookmarks = require "bookmarks"
-- local bookmarks_chrome = require "bookmarks_chrome"
local downloads = require "downloads"
-- local downloads_chrome = require "downloads_chrome"
-- local viewpdf = require "viewpdf"

downloads.add_signal("open-file", function (file)
    luakit.spawn(string.format("xdg-open %q", file))
    return true
end)

local follow = require "follow"
-- local cmdhist = require "cmdhist"
local search = require "search"
-- local taborder = require "taborder"
-- local history = require "history"
-- local history_chrome = require "history_chrome"
-- local help_chrome = require "help_chrome"
-- local binds_chrome = require "binds_chrome"
-- local completion = require "completion"
-- local open_editor = require "open_editor"
-- require "noscript"
local follow_selected = require "follow_selected"
local go_input = require "go_input"
local go_next_prev = require "go_next_prev"
local go_up = require "go_up"

require_web_module("referer_control_wm")
local error_page = require "error_page"
local styles = require "styles"
local hide_scrollbars = require "hide_scrollbars"
local image_css = require "image_css"
-- local newtab_chrome = require "newtab_chrome"
-- local tab_favicons = require "tab_favicons"
-- local view_source = require "view_source"

if pcall(function () lousy.util.find_config("userconf.lua") end) then
    require "userconf"
end

-----------------------------
-- End user script loading --
-----------------------------

-- Do NOT restore previous session – always start clean for kiosk
local w = nil
if w then
    for i, uri in ipairs(uris) do
        w:new_tab(uri, { switch = i == 1 })
    end
else
    window.new(uris)
end

-- vim: et:sw=4:ts=8:sts=4:tw=80
