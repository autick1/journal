--[[
	Гостиничный набор мебели — настройка в Roblox (файл сгенерирован build_hotel_set.py).

	Положи этот Script в ServerScriptService (один на весь набор).
	Скрипт находит в Workspace все импортированные предметы набора и:
	  * ставит материалы и цвета каждой детали (дерево, бархат, латунь, стекло, кирпич...);
	  * закрепляет детали (Anchored);
	  * двери шкафа и комнаты открываются, ящики комода и тумбочки выдвигаются (подсказка E);
	  * часы показывают текущее время, маятник качается;
	  * в камине горит огонь, лампы светят, на банкетку можно сесть.
	Предметы, добавленные в Workspace позже (копии), настраиваются автоматически.
]]

local OPEN_ANGLE = 95        -- угол открывания дверей, градусы
local TIME = 0.6             -- скорость анимации, секунды

-- ключ = { материал, цвет, прозрачность, отражение }
local PALETTE = {
--@PALETTE@
}

-- деталь -> ключ палитры
local PARTS = {
--@PARTS@
}

-- деталь -> поведение
local BEHAVIORS = {
--@BEHAVIORS@
}

local LABELS = {
	Wardrobe = "Шкаф", Dresser = "Комод", Nightstand = "Тумбочка", Door = "Дверь",
}

local TweenService = game:GetService("TweenService")
local RunService = game:GetService("RunService")
local done = {}

local function itemOf(name)
	return name:match("^([^_]+)_")
end

local function bodyOf(model, partName)
	return model:FindFirstChild(itemOf(partName) .. "_Body", true)
end

-- части, двигающиеся вместе: сама деталь и всё, что начинается с «Имя_» (ручки, табличка...)
local function groupOf(model, name)
	local g = {}
	for _, p in ipairs(model:GetDescendants()) do
		if p:IsA("BasePart") and (p.Name == name or p.Name:sub(1, #name + 1) == name .. "_") then
			table.insert(g, p)
		end
	end
	return g
end

-- оси относительно корпуса: поперёк, «вперёд» (к лицу предмета), глубина и ширина детали, вверх
local function axes(ref, part)
	local cf = ref.CFrame
	local s = part.Size
	local dL = (s.X < s.Z) and Vector3.xAxis or Vector3.zAxis
	local lL = (dL == Vector3.xAxis) and Vector3.zAxis or Vector3.xAxis
	local rel = cf:PointToObjectSpace(part.Position)
	local sign = (rel:Dot(dL) >= 0) and 1 or -1
	local depth = (dL == Vector3.xAxis) and s.X or s.Z
	local width = (lL == Vector3.xAxis) and s.X or s.Z
	return cf:VectorToWorldSpace(lL), cf:VectorToWorldSpace(dL) * sign, depth, width, cf.UpVector
end

local function hingeFn(model, main, group)
	local body = bodyOf(model, main.Name) or main
	local lat, front, depth, width, up = axes(body, main)
	local knob
	for _, p in ipairs(group) do
		if p ~= main and (p.Name:find("Knob") or p.Name:find("Handle")) then knob = p end
	end
	local side
	if knob then      -- петли — с противоположной от ручки стороны
		side = ((knob.Position - main.Position):Dot(lat) > 0) and -1 or 1
	else
		side = ((main.Position - body.Position):Dot(lat) > 0) and 1 or -1
	end
	local hinge = main.Position + lat * side * width / 2 - front * depth / 2
	local ang = math.rad(OPEN_ANGLE)
	local function xf(a)
		return CFrame.new(hinge) * CFrame.fromAxisAngle(up, a) * CFrame.new(-hinge)
	end
	if ((xf(ang) * main.CFrame).Position - main.Position):Dot(front) < 0 then ang = -ang end
	return function(alpha) return xf(ang * alpha) end
end

local function slideFn(model, main)
	local body = bodyOf(model, main.Name) or main
	local _, front, depth = axes(body, main)
	return function(alpha) return CFrame.new(front * depth * 0.75 * alpha) end
end

local function makeMover(main, group, fn, label)
	local orig = {}
	for _, p in ipairs(group) do orig[p] = p.CFrame end
	local value = Instance.new("NumberValue")
	value.Name = "OpenAmount"
	value.Parent = main
	value.Changed:Connect(function(a)
		local t = fn(a)
		for p, cf in pairs(orig) do p.CFrame = t * cf end
	end)
	local prompt = Instance.new("ProximityPrompt")
	prompt.ActionText = "Открыть"
	prompt.ObjectText = label
	prompt.MaxActivationDistance = 8
	prompt.RequiresLineOfSight = false
	prompt.Parent = main
	local isOpen = false
	prompt.Triggered:Connect(function()
		isOpen = not isOpen
		prompt.ActionText = isOpen and "Закрыть" or "Открыть"
		TweenService:Create(value, TweenInfo.new(TIME, Enum.EasingStyle.Quad, Enum.EasingDirection.Out),
			{ Value = isOpen and 1 or 0 }):Play()
	end)
end

local function setupClock(model)
	local face = model:FindFirstChild("Clock_Face", true)
	local body = model:FindFirstChild("Clock_Body", true)
	if not (face and body) then return end
	local _, front, _, _, up = axes(body, face)
	local c = face.Position
	local hour = model:FindFirstChild("Clock_HourHand", true)
	local minute = model:FindFirstChild("Clock_MinuteHand", true)
	local pend = model:FindFirstChild("Clock_Pendulum", true)
	local h0, m0, p0 = hour and hour.CFrame, minute and minute.CFrame, pend and pend.CFrame
	local pivot = pend and (pend.Position + up * pend.Size.Y / 2)
	local function rot(center, a)
		return CFrame.new(center) * CFrame.fromAxisAngle(front, a) * CFrame.new(-center)
	end
	RunService.Heartbeat:Connect(function()
		local d = os.date("*t")
		local mins = d.min + d.sec / 60
		local hrs = (d.hour % 12) + mins / 60
		if hour then hour.CFrame = rot(c, -hrs / 12 * 2 * math.pi) * h0 end
		if minute then minute.CFrame = rot(c, -mins / 60 * 2 * math.pi) * m0 end
		if pend then pend.CFrame = rot(pivot, 0.12 * math.sin(os.clock() * math.pi)) * p0 end
	end)
end

local function decorate(p)
	if p.Name:match("_Shade$") then
		local l = Instance.new("PointLight")
		l.Color, l.Brightness, l.Range, l.Shadows = Color3.fromRGB(255, 190, 120), 1.6, 16, true
		l.Parent = p
	elseif p.Name:match("_Fire$") then
		p.CanCollide = false
		local f = Instance.new("Fire")
		f.Size, f.Heat = 3, 6
		f.Color, f.SecondaryColor = Color3.fromRGB(255, 120, 30), Color3.fromRGB(255, 200, 80)
		f.Parent = p
		local l = Instance.new("PointLight")
		l.Color, l.Range, l.Shadows = Color3.fromRGB(255, 140, 60), 20, true
		l.Parent = p
		task.spawn(function()
			while p.Parent do
				l.Brightness = 1.8 + math.random() * 0.9
				task.wait(0.08 + math.random() * 0.1)
			end
		end)
	elseif p.Name:match("_Seat$") then
		local s = Instance.new("Seat")
		s.Name = "SitHere"
		s.Transparency, s.Anchored, s.CanCollide = 1, true, false
		s.Size = Vector3.new(math.min(p.Size.X * 0.7, 3), 0.2, p.Size.Z * 0.6)
		s.CFrame = p.CFrame * CFrame.new(0, p.Size.Y / 2, 0)
		s.Parent = p.Parent
	end
end

local function setupModel(model)
	if done[model] then return end
	done[model] = true
	for _, p in ipairs(model:GetDescendants()) do
		if p:IsA("BasePart") then
			local key = PARTS[p.Name]
			if key then
				local m = PALETTE[key]
				if not p:FindFirstChildOfClass("SurfaceAppearance") then
					p.Material, p.Color = m[1], m[2]
				end
				p.Transparency, p.Reflectance = m[3], m[4]
				p.Anchored = true
				decorate(p)
			end
		end
	end
	for name, kind in pairs(BEHAVIORS) do
		local main = model:FindFirstChild(name, true)
		if main and (kind == "hinge" or kind == "slide") then
			local group = groupOf(model, name)
			local fn = (kind == "hinge") and hingeFn(model, main, group) or slideFn(model, main)
			makeMover(main, group, fn, LABELS[itemOf(name)] or itemOf(name))
		end
	end
	if model:FindFirstChild("Clock_Face", true) then setupClock(model) end
end

local function scan(root)
	for _, p in ipairs(root:GetDescendants()) do
		if p:IsA("BasePart") and PARTS[p.Name] then
			local m = p:FindFirstAncestorOfClass("Model")
			if m then setupModel(m) end
		end
	end
end

scan(workspace)
workspace.ChildAdded:Connect(function(child)
	task.wait(0.5)
	scan(child)
end)
