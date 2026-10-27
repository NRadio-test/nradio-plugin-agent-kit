module("luci.controller.nradio_adv.nradio_compatprobe", package.seeall)

function index()
	if not nixio.fs.access("/etc/config/nradio_compatprobe") then return end
	local page = entry({"nradioadv", "system", "nradio_compatprobe"},
		cbi("nradio_adv/nradio_compatprobe"), _("NRadio Compat Probe"), 99, true)
	page.show = true
	entry({"nradioadv", "system", "nradio_compatprobe", "status"},
		call("action_status"), nil, nil, true).leaf = true
end

function action_status()
	local fs = require "nixio.fs"
	local cur = require "luci.model.uci".cursor()
	local heartbeat = (fs.readfile("/tmp/nradio-compatprobe/status") or ""):gsub("%s+$", "")
	require("luci.nradio").luci_call_result({
		code = 0,
		enabled = cur:get("nradio_compatprobe", "main", "enabled") or "0",
		heartbeat = heartbeat
	})
end
