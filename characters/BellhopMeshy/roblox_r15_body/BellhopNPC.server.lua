-- Script (серверный). Положи внутрь модели Bellhop_R15_Body в Workspace.
-- Коридорный стоит, замечает игрока в радиусе и идёт к нему.
-- Анимации здесь НЕ проигрываются: всё движение тела (походка, руки, пальцы) делает
-- BellhopBody.client.lua у каждого игрока — плавно и без ID анимаций.

local DETECT_RADIUS = 60
local SPEED = 9            -- больше 11 — включается «бег» (наклон, руки вперёд)
local STOP_DISTANCE = 5

local model = script.Parent
local humanoid = model:WaitForChild("Humanoid")
local root = model:WaitForChild("HumanoidRootPart")
humanoid.WalkSpeed = SPEED
root:SetNetworkOwner(nil)
for _, t in ipairs(humanoid:GetPlayingAnimationTracks()) do t:Stop(0) end

while model.Parent do
	local target, best = nil, DETECT_RADIUS
	for _, player in ipairs(game:GetService("Players"):GetPlayers()) do
		local hrp = player.Character and player.Character:FindFirstChild("HumanoidRootPart")
		if hrp then
			local d = (hrp.Position - root.Position).Magnitude
			if d < best then best, target = d, hrp end
		end
	end
	if target and best > STOP_DISTANCE then
		humanoid:MoveTo(target.Position)
	else
		humanoid:MoveTo(root.Position)
	end
	task.wait(0.25)
end
