local m = Map("nradio_compatprobe", translate("NRadio Compat Probe"),
	translate("Lightweight example. The service writes a timestamp to RAM only."))
local s = m:section(NamedSection, "main", "main")
s.addremove = false
local enabled = s:option(Flag, "enabled", translate("Enable"))
enabled.rmempty = false
enabled.default = "0"
local interval = s:option(Value, "interval", translate("Interval in seconds"))
interval.datatype = "range(60,3600)"
interval.rmempty = false
interval.default = "300"
local status = s:option(DummyValue, "_heartbeat", translate("Last heartbeat"))
function status.cfgvalue(self, section)
	return (require("nixio.fs").readfile("/tmp/nradio-compatprobe/status") or "-"):gsub("%s+$", "")
end
function m.on_after_commit(map)
	-- Constant command: no HTTP input is concatenated into a shell command.
	os.execute("/etc/init.d/nradio-compatprobe restart >/dev/null 2>&1")
end
return m
