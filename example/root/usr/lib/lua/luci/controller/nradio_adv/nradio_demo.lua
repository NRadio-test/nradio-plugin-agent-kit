module("luci.controller.nradio_adv.nradio_demo", package.seeall)

function index()
	if not nixio.fs.access("/etc/config/nradio_demo") then return end
	local page = entry({"nradioadv", "system", "nradio_demo"},
		cbi("nradio_adv/nradio_demo"), _("NRadio Demo"), 99, true)
	page.show = true
	entry({"nradioadv", "system", "nradio_demo", "status"},
		call("action_status"), nil, nil, true).leaf = true
end

function action_status()
	local fs = require "nixio.fs"
	local cur = require "luci.model.uci".cursor()
	local heartbeat = (fs.readfile("/tmp/nradio-demo/status") or ""):gsub("%s+$", "")
	require("luci.nradio").luci_call_result({
		code = 0,
		enabled = cur:get("nradio_demo", "main", "enabled") or "0",
		heartbeat = heartbeat
	})
end
