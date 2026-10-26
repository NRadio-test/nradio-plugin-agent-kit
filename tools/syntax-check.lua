for i = 1, #arg do
	local fn, err = loadfile(arg[i])
	assert(fn, err)
	print("Lua syntax OK: " .. arg[i])
end
