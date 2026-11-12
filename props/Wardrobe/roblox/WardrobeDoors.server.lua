--[[
	Шкаф с открывающимися дверями.
	Положи этот Script ВНУТРЬ импортированной модели шкафа (рядом с Wardrobe_Body).

	Что делает:
	  * ставит материалы и цвета (дерево, латунные ручки, металлические петли) — текстуры не нужны;
	  * находит ось петли каждой створки сам (по её размеру и положению относительно корпуса);
	  * добавляет на каждую дверь подсказку «E — Открыть/Закрыть» и плавно её поворачивает.
]]

local OPEN_ANGLE = 100         -- на сколько градусов открывается дверь
local TIME = 0.6               -- длительность анимации, с
local WOOD_COLOR = Color3.fromRGB(120, 70, 38)
local BRASS_COLOR = Color3.fromRGB(205, 160, 75)
local METAL_COLOR = Color3.fromRGB(90, 90, 95)

local TweenService = game:GetService("TweenService")
local model = script.Parent

local function find(name)
	local p = model:FindFirstChild(name, true)
	assert(p, "Не найдена деталь " .. name .. " — проверь, что скрипт лежит внутри модели шкафа")
	return p
end

local body = find("Wardrobe_Body")
local hinges = model:FindFirstChild("Wardrobe_Hinges", true)

-- материалы и физика корпуса
for _, p in ipairs(model:GetDescendants()) do
	if p:IsA("BasePart") then
		if p.Name:find("Knob") then
			p.Material, p.Color = Enum.Material.Metal, BRASS_COLOR
		elseif p.Name:find("Hinge") then
			p.Material, p.Color = Enum.Material.Metal, METAL_COLOR
		else
			p.Material, p.Color = Enum.Material.Wood, WOOD_COLOR
		end
	end
end
body.Anchored = true
if hinges then hinges.Anchored = true end

local function setupDoor(door, knob)
	door.Anchored = true
	if knob then                         -- ручка едет вместе с дверью
		knob.Anchored = false
		knob.CanCollide = false
		local weld = Instance.new("WeldConstraint")
		weld.Part0, weld.Part1 = door, knob
		weld.Parent = knob
	end

	-- ось петли: внешний край створки, задняя сторона (ближе к корпусу)
	local bodyCF = body.CFrame
	local rel = bodyCF:PointToObjectSpace(door.Position)
	local sx = rel.X >= 0 and 1 or -1
	local sz = rel.Z >= 0 and 1 or -1        -- с какой стороны «перед» шкафа
	local half = door.Size / 2
	local hingeLocal = rel + Vector3.new(sx * half.X, 0, -sz * half.Z)
	local hingeCF = bodyCF * CFrame.new(hingeLocal)
	local closed = door.CFrame
	local front = bodyCF:VectorToWorldSpace(Vector3.new(0, 0, sz))

	local function openedCF(sign)
		return hingeCF * CFrame.Angles(0, math.rad(sign * OPEN_ANGLE), 0) * hingeCF:Inverse() * closed
	end
	-- выбираем направление, в котором дверь уходит вперёд, а не внутрь шкафа
	local a, b = openedCF(1), openedCF(-1)
	local opened = ((a.Position - closed.Position):Dot(front) > (b.Position - closed.Position):Dot(front)) and a or b

	local value = Instance.new("CFrameValue")
	value.Value = closed
	value.Changed:Connect(function(cf) door.CFrame = cf end)

	local prompt = Instance.new("ProximityPrompt")
	prompt.ActionText = "Открыть"
	prompt.ObjectText = "Шкаф"
	prompt.MaxActivationDistance = 8
	prompt.Parent = door

	local isOpen = false
	prompt.Triggered:Connect(function()
		isOpen = not isOpen
		prompt.ActionText = isOpen and "Закрыть" or "Открыть"
		TweenService:Create(value, TweenInfo.new(TIME, Enum.EasingStyle.Quad, Enum.EasingDirection.Out),
			{ Value = isOpen and opened or closed }):Play()
	end)
end

setupDoor(find("Wardrobe_Door_L"), model:FindFirstChild("Wardrobe_Knob_L", true))
setupDoor(find("Wardrobe_Door_R"), model:FindFirstChild("Wardrobe_Knob_R", true))
