--[[
	Диван / кресло: материалы, цвета, закрепление и место для сидения.
	Положи этот Script ВНУТРЬ импортированной модели дивана или кресла.
]]
local COLORS = {
	Wood   = Color3.fromRGB(110, 62, 35),    -- ножки, царга, рамка спинки, накладки подлокотников
	Fabric = Color3.fromRGB(140, 22, 32),    -- сиденье, подлокотники, спинка, пуговицы
}
local model = script.Parent
local seatPart
for _, p in ipairs(model:GetDescendants()) do
	if p:IsA("BasePart") then
		local n = p.Name
		local wood = n:find("Leg") or n:find("Base") or n:find("Frame") or n:find("ArmFront")
		p.Material = wood and Enum.Material.Wood or Enum.Material.Fabric
		p.Color = wood and COLORS.Wood or COLORS.Fabric
		p.Anchored = true
		if n:find("Buttons") or n:find("BackPanel") then p.CanCollide = false end
		if n:match("_Seat$") then seatPart = p end
	end
end
-- места для сидения на подушке (у дивана — три, у кресла — одно)
if seatPart then
	local count = seatPart.Size.X > 3 and 3 or 1
	for i = 1, count do
		local s = Instance.new("Seat")
		s.Name = "SitHere" .. i
		s.Transparency, s.Anchored, s.CanCollide = 1, true, false
		s.Size = Vector3.new(seatPart.Size.X / count * 0.8, 0.2, seatPart.Size.Z * 0.6)
		local offset = (i - (count + 1) / 2) * seatPart.Size.X / count
		s.CFrame = seatPart.CFrame * CFrame.new(offset, seatPart.Size.Y / 2, 0)
		s.Parent = model
	end
end
