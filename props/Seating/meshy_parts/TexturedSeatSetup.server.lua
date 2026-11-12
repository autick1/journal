--[[
	Диван / кресло с текстурами (детали из Meshy-модели).
	Положи этот Script ВНУТРЬ импортированной модели.

	Текстуры зашиты в FBX — Import 3D сам создаёт SurfaceAppearance на каждой детали.
	Если какая-то деталь осталась без текстуры, скрипт копирует ей SurfaceAppearance с соседней.
]]
local model = script.Parent
local template, seatPart
local parts = {}

for _, p in ipairs(model:GetDescendants()) do
	if p:IsA("BasePart") then
		table.insert(parts, p)
		template = template or p:FindFirstChildOfClass("SurfaceAppearance")
		if p.Name:match("_Seat$") then seatPart = p end
	end
end

for _, p in ipairs(parts) do
	p.Anchored = true
	if template and p:IsA("MeshPart") and not p:FindFirstChildOfClass("SurfaceAppearance") then
		template:Clone().Parent = p
	end
end

-- места для сидения (у дивана — три, у кресла — одно)
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
