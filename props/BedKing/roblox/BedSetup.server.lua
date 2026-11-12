--[[
	Кровать: материалы, цвета и закрепление деталей.
	Положи этот Script ВНУТРЬ импортированной модели кровати и нажми Play
	(или просто оставь — сработает при запуске игры).
	Цвета меняются в таблице COLORS.
]]

local COLORS = {
	Wood  = Color3.fromRGB(120, 72, 42),   -- каркас: столбики, щиты, карнизы, царги
	Duvet = Color3.fromRGB(140, 25, 35),   -- одеяло и отворот
	Linen = Color3.fromRGB(235, 230, 220), -- матрас, простыня, подушки
}

local model = script.Parent
for _, p in ipairs(model:GetDescendants()) do
	if p:IsA("BasePart") then
		local n = p.Name
		if n:find("Duvet") then
			p.Material, p.Color = Enum.Material.Fabric, COLORS.Duvet
		elseif n:find("Sheet") or n:find("Pillow") or n:find("Mattress") then
			p.Material, p.Color = Enum.Material.Fabric, COLORS.Linen
		else
			p.Material, p.Color = Enum.Material.Wood, COLORS.Wood
		end
		p.Anchored = true
		-- ткань без сложной коллизии (дешевле для физики), матрас — твёрдый
		if n:find("Duvet") or n:find("Sheet") or n:find("Pillow") then
			p.CanCollide = false
		end
	end
end
