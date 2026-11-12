--[[
	Мебель из деталей (резной диван / деревянный стул): цвета, закрепление, места для сидения.
	Положи этот Script ВНУТРЬ импортированной модели.
]]
local WOOD_COLOR   = Color3.fromRGB(105, 58, 30)
local FABRIC_COLOR = Color3.fromRGB(140, 25, 32)
-- мягкие детали (ткань); всё остальное — дерево
local FABRIC = { "Sofa_Seat", "Sofa_Arm_", "Sofa_BackPanel", "Sofa_BackRear" }

local model = script.Parent
local seats = {}

for _, p in ipairs(model:GetDescendants()) do
	if p:IsA("BasePart") then
		local fabric = false
		for _, key in ipairs(FABRIC) do
			if p.Name:find(key, 1, true) then fabric = true end
		end
		if not p:FindFirstChildOfClass("SurfaceAppearance") then
			p.Material = fabric and Enum.Material.Fabric or Enum.Material.Wood
			p.Color = fabric and FABRIC_COLOR or WOOD_COLOR
		end
		p.Anchored = true
		if p.Name:find("Crest") then p.CanCollide = false end
		if p.Name:match("_Seat$") or p.Name:match("_Seat_[LR]$") then table.insert(seats, p) end
	end
end

-- невидимое сиденье на каждой подушке / на сиденье стула
for i, part in ipairs(seats) do
	local s = Instance.new("Seat")
	s.Name = "SitHere" .. i
	s.Transparency, s.Anchored, s.CanCollide = 1, true, false
	s.Size = Vector3.new(math.min(part.Size.X * 0.7, 3), 0.2, part.Size.Z * 0.6)
	s.CFrame = part.CFrame * CFrame.new(0, part.Size.Y / 2, 0)
	s.Parent = model
end
