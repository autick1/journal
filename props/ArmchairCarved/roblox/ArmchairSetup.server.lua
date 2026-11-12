--[[
	Резное кресло: цвета, материалы, закрепление и место для сидения.
	Положи этот Script ВНУТРЬ импортированной модели кресла (рядом с Armchair_Seat).
]]
local WOOD_COLOR   = Color3.fromRGB(105, 58, 30)   -- ножки, царга, свитки, рамка, корона
local FABRIC_COLOR = Color3.fromRGB(140, 25, 32)   -- подушка, подлокотники, спинка

local WOOD = { Leg = true, Base = true, ArmFront = true, BackFrame = true, Crest = true }
local model = script.Parent
local seatPart

for _, p in ipairs(model:GetDescendants()) do
	if p:IsA("BasePart") then
		local key = p.Name:gsub("^Armchair_", ""):gsub("_[LR]$", ""):gsub("_[FB][LR]$", "")
		local wood = WOOD[key] or p.Name:find("Leg_") ~= nil
		if not p:FindFirstChildOfClass("SurfaceAppearance") then
			p.Material = wood and Enum.Material.Wood or Enum.Material.Fabric
			p.Color = wood and WOOD_COLOR or FABRIC_COLOR
		end
		p.Anchored = true
		if p.Name:find("Crest") then p.CanCollide = false end
		if p.Name:match("_Seat$") then seatPart = p end
	end
end

-- невидимое сиденье на подушке: игрок садится, нажав на кресло / подойдя к нему
if seatPart then
	local s = Instance.new("Seat")
	s.Name = "SitHere"
	s.Transparency, s.Anchored, s.CanCollide = 1, true, false
	s.Size = Vector3.new(seatPart.Size.X * 0.7, 0.2, seatPart.Size.Z * 0.6)
	s.CFrame = seatPart.CFrame * CFrame.new(0, seatPart.Size.Y / 2, 0)
	s.Parent = model
end
