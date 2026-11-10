-- Script (серверный). Положи внутрь модели Bellhop_R15 в Workspace.
-- Коридорный стоит (idle), замечает игрока в радиусе и идёт к нему (walk).
-- Анимации — стандартные R15 от Roblox; свои можно сделать в Animation Editor и вставить их ID.

local IDLE_ANIM = 507766388   -- стандартная R15 idle
local WALK_ANIM = 507777826   -- стандартная R15 walk
local DETECT_RADIUS = 60
local SPEED = 10

local model = script.Parent
local humanoid = model:WaitForChild("Humanoid")
local root = model:WaitForChild("HumanoidRootPart")
local animator = humanoid:FindFirstChildOfClass("Animator") or Instance.new("Animator", humanoid)

local function load(id)
	local anim = Instance.new("Animation")
	anim.AnimationId = "rbxassetid://" .. id
	return animator:LoadAnimation(anim)
end

local idle, walk = load(IDLE_ANIM), load(WALK_ANIM)
idle.Looped, walk.Looped = true, true
idle:Play()
humanoid.WalkSpeed = SPEED
root:SetNetworkOwner(nil)

humanoid.Running:Connect(function(speed)
	if speed > 0.5 then
		if not walk.IsPlaying then walk:Play(0.2) end
		walk:AdjustSpeed(speed / 12)
	elseif walk.IsPlaying then
		walk:Stop(0.2)
	end
end)

while model.Parent do
	local target, best = nil, DETECT_RADIUS
	for _, player in ipairs(game:GetService("Players"):GetPlayers()) do
		local hrp = player.Character and player.Character:FindFirstChild("HumanoidRootPart")
		if hrp then
			local d = (hrp.Position - root.Position).Magnitude
			if d < best then best, target = d, hrp end
		end
	end
	if target then humanoid:MoveTo(target.Position) end
	task.wait(0.25)
end
