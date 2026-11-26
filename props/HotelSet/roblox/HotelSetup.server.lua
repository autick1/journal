--[[
	Гостиничный набор мебели — настройка в Roblox (файл сгенерирован build_hotel_set.py).

	Положи этот Script в ServerScriptService (один на весь набор).
	Скрипт находит в Workspace все импортированные предметы набора и:
	  * ставит материалы и цвета каждой детали (дерево, бархат, латунь, стекло, кирпич...);
	  * закрепляет детали (Anchored);
	  * двери шкафа и комнаты открываются, ящики комода и тумбочки выдвигаются (подсказка E);
	  * часы показывают текущее время, маятник качается;
	  * паровой котёл: вентиль крутится (E), стрелка манометра дрожит и подскакивает, из трубы дым;
	  * звонок портье: нажатие (E или клик) — кнопка уходит вниз и пружинит, купол дрожит, звучит BELL_SOUND;
	  * в камине горит огонь, лампы, бра и люстра светят, на банкетку можно сесть.
	Предметы, добавленные в Workspace позже (копии), настраиваются автоматически.
]]

local OPEN_ANGLE = 95        -- угол открывания дверей, градусы
local TIME = 0.6             -- скорость анимации, секунды
local BELL_SOUND = ""        -- звук звонка: "rbxassetid://ID" из Toolbox (Audio). Пусто — без звука
local TIME_ZONE = 3          -- часовой пояс для часов: Москва = 3. nil = время сервера (UTC)

-- ключ = { материал, цвет, прозрачность, отражение }
local PALETTE = {
	Wood = { Enum.Material.Wood, Color3.fromRGB(88, 38, 27), 0, 0 },
	WoodDark = { Enum.Material.Wood, Color3.fromRGB(56, 24, 17), 0, 0 },
	Fabric = { Enum.Material.Fabric, Color3.fromRGB(122, 22, 34), 0, 0 },
	FabricDark = { Enum.Material.Fabric, Color3.fromRGB(72, 14, 24), 0, 0 },
	Brass = { Enum.Material.Metal, Color3.fromRGB(196, 140, 72), 0, 0 },
	Iron = { Enum.Material.Metal, Color3.fromRGB(52, 50, 48), 0, 0 },
	Glass = { Enum.Material.Glass, Color3.fromRGB(190, 200, 205), 0.7, 0 },
	Mirror = { Enum.Material.Glass, Color3.fromRGB(185, 192, 198), 0.1, 0.6 },
	Leaf = { Enum.Material.LeafyGrass, Color3.fromRGB(38, 66, 34), 0, 0 },
	Terracotta = { Enum.Material.Slate, Color3.fromRGB(150, 78, 52), 0, 0 },
	Soil = { Enum.Material.Ground, Color3.fromRGB(48, 34, 24), 0, 0 },
	Shade = { Enum.Material.Fabric, Color3.fromRGB(226, 192, 150), 0, 0 },
	Leather = { Enum.Material.Leather, Color3.fromRGB(62, 36, 46), 0, 0 },
	Strap = { Enum.Material.Leather, Color3.fromRGB(122, 70, 40), 0, 0 },
	Brick = { Enum.Material.Brick, Color3.fromRGB(122, 56, 40), 0, 0 },
	Mortar = { Enum.Material.Concrete, Color3.fromRGB(40, 30, 26), 0, 0 },
	Log = { Enum.Material.Wood, Color3.fromRGB(66, 44, 30), 0, 0 },
	Fire = { Enum.Material.Neon, Color3.fromRGB(255, 140, 40), 0.25, 0 },
	Paper = { Enum.Material.SmoothPlastic, Color3.fromRGB(232, 220, 196), 0, 0 },
	Black = { Enum.Material.SmoothPlastic, Color3.fromRGB(22, 18, 16), 0, 0 },
	Canvas = { Enum.Material.SmoothPlastic, Color3.fromRGB(90, 90, 80), 0, 0 },
	Rug = { Enum.Material.Fabric, Color3.fromRGB(110, 20, 28), 0, 0 },
	Wax = { Enum.Material.SmoothPlastic, Color3.fromRGB(236, 228, 206), 0, 0 },
	Flame = { Enum.Material.Neon, Color3.fromRGB(255, 190, 90), 0.1, 0 },
	Ink = { Enum.Material.SmoothPlastic, Color3.fromRGB(72, 30, 20), 0, 0 },
	Rust = { Enum.Material.CorrodedMetal, Color3.fromRGB(74, 36, 30), 0, 0 },
	RedPaint = { Enum.Material.CorrodedMetal, Color3.fromRGB(150, 24, 20), 0, 0 },
	Hidden = { Enum.Material.SmoothPlastic, Color3.fromRGB(0, 0, 0), 1, 0 }
}

-- деталь -> ключ палитры
local PARTS = {
	["Wardrobe_Body"] = "Wood",
	["Wardrobe_Rail"] = "Brass",
	["Wardrobe_DoorL"] = "Wood",
	["Wardrobe_DoorL_Knob"] = "WoodDark",
	["Wardrobe_DoorR"] = "Wood",
	["Wardrobe_DoorR_Knob"] = "WoodDark",
	["Bookcase_Body"] = "Wood",
	["LuggageCart_Deck"] = "Wood",
	["LuggageCart_Carpet"] = "Fabric",
	["LuggageCart_Frame"] = "Brass",
	["LuggageCart_Wheels"] = "Iron",
	["CoatRack_Body"] = "Wood",
	["Plant_Pot"] = "Terracotta",
	["Plant_Soil"] = "Soil",
	["Plant_Trunk"] = "WoodDark",
	["Plant_Leaves"] = "Leaf",
	["Suitcase_Body"] = "Leather",
	["Suitcase_Straps"] = "Strap",
	["Suitcase_Brass"] = "Brass",
	["Painting_Frame"] = "Wood",
	["Painting_Canvas"] = "Canvas",
	["FloorLamp_Body"] = "Wood",
	["FloorLamp_Trim"] = "Brass",
	["FloorLamp_Shade"] = "Shade",
	["TableLamp_Body"] = "Wood",
	["TableLamp_Trim"] = "Brass",
	["TableLamp_Shade"] = "Shade",
	["Dresser_Body"] = "Wood",
	["Dresser_Drawer2"] = "Wood",
	["Dresser_Drawer2_Knobs"] = "Brass",
	["Dresser_Drawer1"] = "Wood",
	["Dresser_Drawer1_Knobs"] = "Brass",
	["Nightstand_Body"] = "Wood",
	["Nightstand_Drawer2"] = "Wood",
	["Nightstand_Drawer2_Knobs"] = "Brass",
	["Nightstand_Drawer1"] = "Wood",
	["Nightstand_Drawer1_Knobs"] = "Brass",
	["CoffeeTable_Body"] = "Wood",
	["Bench_Seat"] = "Fabric",
	["Bench_Body"] = "Wood",
	["Bench_Buttons"] = "FabricDark",
	["Door_Body"] = "Wood",
	["Door_Leaf"] = "Wood",
	["Door_Leaf_Plate"] = "Brass",
	["Door_Leaf_Number"] = "Black",
	["Door_Leaf_Handle"] = "Brass",
	["Fireplace_Body"] = "Wood",
	["Fireplace_Back"] = "Mortar",
	["Fireplace_Bricks"] = "Brick",
	["Fireplace_Grate"] = "Iron",
	["Fireplace_Logs"] = "Log",
	["Fireplace_Fire"] = "Fire",
	["Clock_Body"] = "Wood",
	["Clock_Glass"] = "Glass",
	["Clock_Brass"] = "Brass",
	["Clock_Face"] = "Paper",
	["Clock_Numerals"] = "Black",
	["Clock_HourHand"] = "Black",
	["Clock_MinuteHand"] = "Black",
	["Clock_Pendulum"] = "Brass",
	["Clock_Weights"] = "Brass",
	["Mirror_Stand"] = "Wood",
	["Mirror_Pins"] = "Brass",
	["Mirror_Frame"] = "Wood",
	["Mirror_Glass"] = "Mirror",
	["LuggageRack_Frame"] = "Wood",
	["LuggageRack_Casters"] = "Brass",
	["LuggageRack_Wheels"] = "Iron",
	["LuggageRack_Case1_Body"] = "Leather",
	["LuggageRack_Case1_Straps"] = "Strap",
	["LuggageRack_Case1_Brass"] = "Brass",
	["LuggageRack_Case2_Body"] = "Leather",
	["LuggageRack_Case2_Straps"] = "Strap",
	["LuggageRack_Case2_Brass"] = "Brass",
	["Curtains_Pelmet"] = "Wood",
	["Curtains_Rod"] = "Brass",
	["Curtains_Left"] = "Fabric",
	["Curtains_Tiebacks"] = "Brass",
	["Curtains_Right"] = "Fabric",
	["WallPanel_Body"] = "Wood",
	["WallPanel_Diamonds"] = "Fabric",
	["WallPanel_DiamondsDark"] = "FabricDark",
	["Chandelier_Body"] = "Wood",
	["Chandelier_Chain"] = "Iron",
	["Chandelier_Arms"] = "Wood",
	["Chandelier_Candles"] = "Wax",
	["Chandelier_Flames"] = "Flame",
	["Rug_Body"] = "Rug",
	["Sconce_Body"] = "Wood",
	["Sconce_Trim"] = "Brass",
	["Sconce_Arms"] = "WoodDark",
	["Sconce_Candles"] = "Wax",
	["Sconce_Shades"] = "Shade",
	["RoundTable_Body"] = "Wood",
	["RectTable_Body"] = "Wood",
	["GrandClock_Body"] = "Wood",
	["GrandClock_Glass"] = "Glass",
	["GrandClock_Brass"] = "Brass",
	["GrandClock_Face"] = "Paper",
	["GrandClock_Numerals"] = "Black",
	["GrandClock_HourHand"] = "Black",
	["GrandClock_MinuteHand"] = "Black",
	["GrandClock_Pendulum"] = "Brass",
	["GrandClock_Weights"] = "Brass",
	["WallClock_Body"] = "Wood",
	["WallClock_Face"] = "Paper",
	["WallClock_Numerals"] = "Black",
	["WallClock_Cap"] = "Brass",
	["WallClock_HourHand"] = "Black",
	["WallClock_MinuteHand"] = "Black",
	["FacetClock_Body"] = "Wood",
	["FacetClock_Rim"] = "WoodDark",
	["FacetClock_Face"] = "Paper",
	["FacetClock_Ticks"] = "Ink",
	["FacetClock_HourHand"] = "Ink",
	["FacetClock_MinuteHand"] = "Ink",
	["FacetClock_Cap"] = "Ink",
	["ReceptionDesk_Body"] = "Wood",
	["ReceptionDesk_Inset"] = "Leather",
	["ReceptionDesk_InsetTrim"] = "Brass",
	["ReceptionDesk_DrawerL1"] = "Wood",
	["ReceptionDesk_DrawerL1_Knobs"] = "Brass",
	["ReceptionDesk_DrawerL2"] = "Wood",
	["ReceptionDesk_DrawerL2_Knobs"] = "Brass",
	["ReceptionDesk_DrawerR1"] = "Wood",
	["ReceptionDesk_DrawerR1_Knobs"] = "Brass",
	["ReceptionDesk_DrawerR2"] = "Wood",
	["ReceptionDesk_DrawerR2_Knobs"] = "Brass",
	["ReceptionDesk_DrawerC"] = "Wood",
	["ReceptionDesk_DrawerC_Knobs"] = "Brass",
	["ReceptionDesk_BellBase"] = "WoodDark",
	["ReceptionDesk_BellDome"] = "Brass",
	["ReceptionDesk_BellButton"] = "Brass",
	["DeskBell_Base"] = "WoodDark",
	["DeskBell_Dome"] = "Brass",
	["DeskBell_Button"] = "Brass",
	["GrandChandelier_Body"] = "Wood",
	["GrandChandelier_Trim"] = "Brass",
	["GrandChandelier_Chain"] = "Wood",
	["GrandChandelier_Arms"] = "Wood",
	["GrandChandelier_Sockets"] = "WoodDark",
	["GrandChandelier_Shades"] = "Shade",
	["GrandChandelier_ShadeFrames"] = "WoodDark",
	["Locker_Body"] = "Rust",
	["Locker_Rod"] = "Iron",
	["Locker_Hinges"] = "Iron",
	["Locker_DoorL"] = "Rust",
	["Locker_DoorL_Vents"] = "Black",
	["Locker_DoorL_Handle"] = "Iron",
	["Locker_DoorL_HandleHole"] = "Black",
	["Locker_DoorR"] = "Rust",
	["Locker_DoorR_Vents"] = "Black",
	["Locker_DoorR_Handle"] = "Iron",
	["Locker_DoorR_HandleHole"] = "Black",
	["Boiler_Body"] = "Rust",
	["Boiler_Rivets"] = "Rust",
	["Boiler_Firebox"] = "Mortar",
	["Boiler_Grate"] = "Iron",
	["Boiler_Fire"] = "Fire",
	["Boiler_Door"] = "Rust",
	["Boiler_Door_Vents"] = "Black",
	["Boiler_Door_Handle"] = "Iron",
	["Boiler_Pipes"] = "Rust",
	["Boiler_SmokeOut"] = "Hidden",
	["Boiler_Gauge"] = "Iron",
	["Boiler_GaugeRim"] = "Brass",
	["Boiler_GaugeFace"] = "Paper",
	["Boiler_GaugeTicks"] = "Black",
	["Boiler_GaugeNeedle"] = "Fire",
	["Boiler_Valve"] = "RedPaint"
}

-- деталь -> поведение
local BEHAVIORS = {
	["Wardrobe_DoorL"] = "hinge",
	["Wardrobe_DoorR"] = "hinge",
	["Dresser_Drawer2"] = "slide",
	["Dresser_Drawer1"] = "slide",
	["Nightstand_Drawer2"] = "slide",
	["Nightstand_Drawer1"] = "slide",
	["Door_Leaf"] = "hinge",
	["Clock_Pendulum"] = "pendulum",
	["Clock_HourHand"] = "hour",
	["Clock_MinuteHand"] = "minute",
	["Chandelier_Flames"] = "light",
	["GrandClock_HourHand"] = "hour",
	["GrandClock_MinuteHand"] = "minute",
	["GrandClock_Pendulum"] = "pendulum",
	["WallClock_HourHand"] = "hour",
	["WallClock_MinuteHand"] = "minute",
	["FacetClock_HourHand"] = "hour",
	["FacetClock_MinuteHand"] = "minute",
	["ReceptionDesk_DrawerL1"] = "slide",
	["ReceptionDesk_DrawerL2"] = "slide",
	["ReceptionDesk_DrawerR1"] = "slide",
	["ReceptionDesk_DrawerR2"] = "slide",
	["ReceptionDesk_DrawerC"] = "slide",
	["ReceptionDesk_BellButton"] = "press",
	["DeskBell_Button"] = "press",
	["Locker_DoorL"] = "hinge",
	["Locker_DoorR"] = "hinge",
	["Boiler_Door"] = "hinge",
	["Boiler_GaugeNeedle"] = "gauge",
	["Boiler_Valve"] = "spin"
}

local LABELS = {
	Wardrobe = "Шкаф", Dresser = "Комод", Nightstand = "Тумбочка", Door = "Дверь", ReceptionDesk = "Стол", Locker = "Шкафчик",
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

local function setupClock(model, item)
	local face = model:FindFirstChild(item .. "_Face", true)
	local body = model:FindFirstChild(item .. "_Body", true)
	if not face then return end
	local fs = face.Size                         -- ось циферблата = самая тонкая сторона, к стрелкам
	local ax, mn = Vector3.xAxis, fs.X
	if fs.Y < mn then ax, mn = Vector3.yAxis, fs.Y end
	if fs.Z < mn then ax = Vector3.zAxis end
	local front = face.CFrame:VectorToWorldSpace(ax)
	local up = Vector3.yAxis
	local c = face.Position
	local hour = model:FindFirstChild(item .. "_HourHand", true)
	local minute = model:FindFirstChild(item .. "_MinuteHand", true)
	local pend = model:FindFirstChild(item .. "_Pendulum", true)
	local h0, m0, p0 = hour and hour.CFrame, minute and minute.CFrame, pend and pend.CFrame
	local pivot = pend and (pend.Position + up * pend.Size.Y / 2)
	local function rot(center, a)
		return CFrame.new(center) * CFrame.fromAxisAngle(front, a) * CFrame.new(-center)
	end
	local ref = hour or minute
	if ref and (ref.Position - c):Dot(front) < 0 then front = -front end
	RunService.Heartbeat:Connect(function()
		local d = TIME_ZONE and os.date("!*t", os.time() + TIME_ZONE * 3600) or os.date("*t")
		local mins = d.min + d.sec / 60
		local hrs = (d.hour % 12) + mins / 60
		if hour then hour.CFrame = rot(c, -hrs / 12 * 2 * math.pi) * h0 end
		if minute then minute.CFrame = rot(c, -mins / 60 * 2 * math.pi) * m0 end
		if pend then pend.CFrame = rot(pivot, 0.12 * math.sin(os.clock() * math.pi)) * p0 end
	end)
end

local function setupPress(model, button)
	local prefix = button.Name:gsub("Button$", "")          -- ReceptionDesk_Bell / DeskBell_
	local dome = model:FindFirstChild(prefix .. "Dome", true)
	local up = Vector3.yAxis
	local b0 = button.CFrame
	local d0 = dome and dome.CFrame
	local depth = button.Size.Y * 0.45                       -- ход кнопки
	button.CanCollide = false
	local sound
	if BELL_SOUND ~= "" then
		sound = Instance.new("Sound")
		sound.SoundId, sound.Volume, sound.RollOffMaxDistance = BELL_SOUND, 0.8, 60
		sound.Parent = dome or button
	end
	local busy = false
	local function ring()
		if busy then return end
		busy = true
		local down = TweenService:Create(button, TweenInfo.new(0.06, Enum.EasingStyle.Quad, Enum.EasingDirection.In),
			{ CFrame = b0 - up * depth })
		down:Play()
		down.Completed:Wait()
		if sound then sound:Play() end
		local back = TweenService:Create(button, TweenInfo.new(0.18, Enum.EasingStyle.Back, Enum.EasingDirection.Out),
			{ CFrame = b0 })
		back:Play()
		if dome then                                         -- купол «звенит» — затухающая дрожь
			for i = 1, 8 do
				local a = math.rad(1.5) * (1 - i / 9) * ((i % 2 == 0) and 1 or -1)
				dome.CFrame = d0 * CFrame.Angles(a, 0, a * 0.6)
				task.wait(0.025)
			end
			dome.CFrame = d0
		end
		back.Completed:Wait()
		busy = false
	end
	local prompt = Instance.new("ProximityPrompt")
	prompt.ActionText, prompt.ObjectText = "Позвонить", "Звонок"
	prompt.MaxActivationDistance, prompt.RequiresLineOfSight = 8, false
	prompt.Parent = dome or button
	prompt.Triggered:Connect(ring)
	local click = Instance.new("ClickDetector")
	click.MaxActivationDistance = 12
	click.Parent = dome or button
	click.MouseClick:Connect(ring)
end

local function thinAxis(part)                -- ось «из плоскости» детали = самая тонкая сторона
	local s = part.Size
	local ax = (s.X <= s.Y and s.X <= s.Z) and Vector3.xAxis or ((s.Y <= s.Z) and Vector3.yAxis or Vector3.zAxis)
	return part.CFrame:VectorToWorldSpace(ax)
end

local function setupSpin(model, main)             -- вентиль: полтора оборота по E, «давление» растёт
	local axis = thinAxis(main)
	local c0 = main.CFrame
	local value = Instance.new("NumberValue")
	value.Name = "SpinAngle"
	value.Parent = main
	value.Changed:Connect(function(a)
		main.CFrame = CFrame.new(c0.Position) * CFrame.fromAxisAngle(axis, a) * (c0 - c0.Position)
	end)
	local prompt = Instance.new("ProximityPrompt")
	prompt.ActionText, prompt.ObjectText = "Крутить вентиль", "Котёл"
	prompt.MaxActivationDistance, prompt.RequiresLineOfSight = 8, false
	prompt.Parent = main
	local busy = false
	prompt.Triggered:Connect(function()
		if busy then return end
		busy = true
		local tw = TweenService:Create(value, TweenInfo.new(1.2, Enum.EasingStyle.Quad, Enum.EasingDirection.InOut),
			{ Value = value.Value + math.pi * 3 })
		tw:Play()
		model:SetAttribute("Pressure", 1)
		tw.Completed:Wait()
		busy = false
	end)
end

local function setupGauge(model, needle)          -- стрелка манометра: дрожит, после вентиля подскакивает
	local face = model:FindFirstChild(itemOf(needle.Name) .. "_GaugeFace", true)
	if not face then return end
	local n = thinAxis(face)
	if (needle.Position - face.Position):Dot(n) < 0 then n = -n end   -- нормаль к зрителю
	local c = face.Position
	local n0 = needle.CFrame
	local pressure = 0
	RunService.Heartbeat:Connect(function(dt)
		local p = model:GetAttribute("Pressure")
		if p and p > 0 then
			pressure = math.min(1, pressure + p * 0.6)
			model:SetAttribute("Pressure", 0)
		end
		pressure = pressure * (1 - dt * 0.12)
		local t = os.clock()
		local a = -(0.9 + 2.6 * pressure) + 0.06 * math.sin(t * 9) + 0.03 * math.sin(t * 23)
		needle.CFrame = CFrame.new(c) * CFrame.fromAxisAngle(n, a + 2.36) * CFrame.new(-c) * n0   -- по часовой от «7 часов»
	end)
end

local function decorate(p)
	if p.Name:match("_Shades?$") or p.Name:match("_Flames$") then
		local l = Instance.new("PointLight")
		l.Color, l.Brightness, l.Range, l.Shadows = Color3.fromRGB(255, 190, 120), 1.6, 16, true
		l.Parent = p
	elseif p.Name:match("_SmokeOut$") then
		p.CanCollide = false
		local sm = Instance.new("Smoke")
		sm.Color, sm.Opacity, sm.RiseVelocity, sm.Size = Color3.fromRGB(70, 65, 60), 0.25, 4, 2
		sm.Parent = p
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
	for name, kind in pairs(BEHAVIORS) do          -- часы: стрелки и маятник
		if kind == "hour" and model:FindFirstChild(name, true) then setupClock(model, itemOf(name)) end
		if kind == "spin" then
			local b = model:FindFirstChild(name, true)
			if b then setupSpin(model, b) end
		end
		if kind == "gauge" then
			local b = model:FindFirstChild(name, true)
			if b then setupGauge(model, b) end
		end
		if kind == "press" then
			local b = model:FindFirstChild(name, true)
			if b then setupPress(model, b) end
		end
	end
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
