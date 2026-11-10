-- Вставь в Command Bar Roblox Studio (View -> Command Bar) ПОСЛЕ импорта Bellhop_R15.fbx
-- и загрузки 4 текстур (Asset Manager / Import). Впиши ID картинок ниже и нажми Enter.

local IDS = {
	Color     = 0, -- ID картинки Bellhop_Color.png
	Metalness = 0, -- ID Bellhop_Metalness.png
	Roughness = 0, -- ID Bellhop_Roughness.png
	Normal    = 0, -- ID Bellhop_Normal.png
}

local model = workspace:FindFirstChild("Bellhop_R15") or game.Selection:Get()[1]
assert(model, "Выдели импортированную модель в Explorer или назови её Bellhop_R15")

local count = 0
for _, part in ipairs(model:GetDescendants()) do
	if part:IsA("MeshPart") then
		if part.Name == "HumanoidRootPart" then
			part.Transparency = 1
			part.CanCollide = false
		elseif part.Name == "Eyes" then
			part.Material = Enum.Material.Neon
			part.Color = Color3.fromRGB(255, 245, 225)
			part.CastShadow = false
			if not part:FindFirstChildOfClass("PointLight") then
				local light = Instance.new("PointLight")
				light.Color = Color3.fromRGB(255, 240, 220)
				light.Brightness = 2
				light.Range = 6
				light.Parent = part
			end
		else
			local sa = part:FindFirstChildOfClass("SurfaceAppearance") or Instance.new("SurfaceAppearance")
			sa.ColorMap     = "rbxassetid://" .. IDS.Color
			sa.MetalnessMap = "rbxassetid://" .. IDS.Metalness
			sa.RoughnessMap = "rbxassetid://" .. IDS.Roughness
			sa.NormalMap    = "rbxassetid://" .. IDS.Normal
			sa.Parent = part
			count += 1
		end
		part.Anchored = false
	end
end

local lighting = game:GetService("Lighting")
if not lighting:FindFirstChildOfClass("BloomEffect") then
	local bloom = Instance.new("BloomEffect")
	bloom.Intensity, bloom.Size, bloom.Threshold = 1, 24, 0.9
	bloom.Parent = lighting
end
print(("Bellhop: текстуры на %d частях, глаза Neon, Bloom добавлен"):format(count))
