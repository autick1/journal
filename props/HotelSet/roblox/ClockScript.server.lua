--[[
	Часы (FacetClock / WallClock / GrandClock / Clock) — отдельный скрипт.
	Положи этот Script ВНУТРЬ импортированной модели часов (туда же, где лежат детали *_Face, *_HourHand...).

	Что делает:
	  * красит детали (дерево, светлый циферблат, тёмные риски и стрелки, латунь, стекло);
	  * закрепляет все детали (Anchored), чтобы стрелки не падали;
	  * стрелки показывают текущее время в твоём часовом поясе, маятник (если есть) качается.

	Если в ServerScriptService лежит HotelSetup.server.lua — он тоже крутит стрелки.
	Используй ЛИБО его, ЛИБО этот скрипт (иначе стрелки будут дёргаться).
]]

local TIME_ZONE = 3          -- часовой пояс: Москва = 3, Киев = 2, Екатеринбург = 5. nil = время сервера (UTC)
local SET_COLORS = true      -- false — не трогать цвета/материалы

local RunService = game:GetService("RunService")
local model = script.Parent

local parts = {}
for _, d in ipairs(model:GetDescendants()) do
	if d:IsA("BasePart") then table.insert(parts, d) end
end

local function find(pattern)
	for _, p in ipairs(parts) do
		if p.Name:find(pattern) then return p end
	end
end

local face = find("_Face")
local hour = find("_HourHand")
local minute = find("_MinuteHand")
local pend = find("_Pendulum")
assert(face, "Часы: не найдена деталь *_Face. Скрипт должен лежать внутри модели часов, детали не объединять.")
assert(hour or minute, "Часы: не найдены стрелки *_HourHand / *_MinuteHand.")

-- цвета: первое совпадение по имени детали
local LOOK = {
	{ "_Face",    Enum.Material.SmoothPlastic, Color3.fromRGB(240, 230, 200), 0 },
	{ "Hand",     Enum.Material.SmoothPlastic, Color3.fromRGB(62, 28, 18), 0 },
	{ "Tick",     Enum.Material.SmoothPlastic, Color3.fromRGB(62, 28, 18), 0 },
	{ "Numeral",  Enum.Material.SmoothPlastic, Color3.fromRGB(30, 22, 18), 0 },
	{ "_Cap",     Enum.Material.SmoothPlastic, Color3.fromRGB(62, 28, 18), 0 },
	{ "_Rim",     Enum.Material.Wood,          Color3.fromRGB(56, 24, 17), 0 },
	{ "Glass",    Enum.Material.Glass,         Color3.fromRGB(190, 200, 205), 0.7 },
	{ "Brass",    Enum.Material.Metal,         Color3.fromRGB(196, 140, 72), 0 },
	{ "Pendulum", Enum.Material.Metal,         Color3.fromRGB(196, 140, 72), 0 },
	{ "Weight",   Enum.Material.Metal,         Color3.fromRGB(196, 140, 72), 0 },
	{ "",         Enum.Material.Wood,          Color3.fromRGB(88, 38, 27), 0 },   -- всё остальное — дерево
}

for _, p in ipairs(parts) do
	p.Anchored = true
	if p == hour or p == minute or p == pend then p.CanCollide = false end
	if SET_COLORS and not p:FindFirstChildOfClass("SurfaceAppearance") then
		for _, l in ipairs(LOOK) do
			if p.Name:find(l[1]) then
				p.Material, p.Color, p.Transparency = l[2], l[3], l[4]
				break
			end
		end
	end
end

-- ось циферблата = самая тонкая сторона детали Face; направлена туда, где стрелки (к зрителю)
local s = face.Size
local axis, m = Vector3.xAxis, s.X
if s.Y < m then axis, m = Vector3.yAxis, s.Y end
if s.Z < m then axis = Vector3.zAxis end
local normal = face.CFrame:VectorToWorldSpace(axis)
local ref = hour or minute
if (ref.Position - face.Position):Dot(normal) < 0 then normal = -normal end
local center = face.Position
local up = Vector3.yAxis

local h0, m0, p0 = hour and hour.CFrame, minute and minute.CFrame, pend and pend.CFrame
local pivot = pend and (pend.Position + up * pend.Size.Y / 2)

local function rot(c, axisVec, a)
	return CFrame.new(c) * CFrame.fromAxisAngle(axisVec, a) * CFrame.new(-c)
end

local function now()
	if TIME_ZONE then
		return os.date("!*t", os.time() + TIME_ZONE * 3600)
	end
	return os.date("*t")
end

RunService.Heartbeat:Connect(function()
	local t = now()
	local mins = t.min + t.sec / 60
	local hrs = (t.hour % 12) + mins / 60
	-- по часовой стрелке, если смотреть на циферблат спереди
	if hour then hour.CFrame = rot(center, normal, -hrs / 12 * 2 * math.pi) * h0 end
	if minute then minute.CFrame = rot(center, normal, -mins / 60 * 2 * math.pi) * m0 end
	if pend then pend.CFrame = rot(pivot, normal, 0.12 * math.sin(os.clock() * math.pi)) * p0 end
end)
