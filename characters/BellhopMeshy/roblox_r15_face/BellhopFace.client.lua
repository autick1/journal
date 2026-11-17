--[[
	Живое лицо коридорного — LocalScript.
	Положи в StarterPlayer > StarterPlayerScripts. Работает для всех коридорных в Workspace
	(модель Bellhop_R15_Face с костями Jaw / LeftEye / RightEye / HatBone внутри Head).

	Что делает (у каждого игрока на экране, плавно, поверх обычных анимаций):
	  * голова поворачивается к игроку (шея), иногда резко и жутко склоняется набок;
	  * глаза следят за игроком и моргают, при крике вспыхивают красным;
	  * челюсть дышит, вблизи щёлкает зубами, иногда распахивается в оскал-крик;
	  * фуражка покачивается и подпрыгивает при крике;
	  * грудь «дышит» (лёгкий наклон корпуса).
	Настройки — в таблице CFG ниже.
]]

local Players = game:GetService("Players")
local RunService = game:GetService("RunService")
local player = Players.LocalPlayer

local CFG = {
	LOOK_RADIUS = 45,                  -- с какого расстояния (стады) замечает игрока
	NEAR_RADIUS = 14,                  -- ближе — щёлкает зубами
	HEAD_MAX = math.rad(60),           -- максимальный поворот головы
	EYE_MAX = math.rad(8),             -- насколько далеко «бегают» глаза
	JAW_MAX = math.rad(34),            -- полностью открытый рот
	SCREAM_EVERY = { 5, 11 },          -- раз в сколько секунд крик (когда игрок рядом)
	SCREAM_TIME = 0.9,                 -- длительность крика
	TWITCH_EVERY = { 2.5, 7 },         -- раз в сколько секунд резкий наклон головы
	BLINK_EVERY = { 1.8, 5 },          -- моргание
	EYE_COLOR = Color3.fromRGB(255, 245, 225),
	EYE_SCREAM = Color3.fromRGB(255, 40, 30),
	SCREAM_SOUND = "",                 -- "rbxassetid://ID" — звук крика (необязательно)
}

local rigs = {}
local rng = Random.new()

local function rand(range) return rng:NextNumber(range[1], range[2]) end

local function findBone(model, name)
	local b = model:FindFirstChild(name, true)
	if b and (b:IsA("Bone") or b:IsA("Motor6D")) then return b end
	return nil
end

-- мировая система координат сустава в покое (кость или Motor6D), без текущей анимации
local function restFrame(j)
	if j:IsA("Bone") then
		return j.WorldCFrame * j.Transform:Inverse()
	end
	return j.Part0.CFrame * j.C0
end

-- поворот сустава вокруг мирового вектора axis на угол a (с учётом того, кость это или Motor6D)
local function setRot(j, axisWorld, a, extra)
	local axis = restFrame(j):VectorToObjectSpace(axisWorld)
	local cf = CFrame.fromAxisAngle(axis.Unit, a)
	if extra then cf = cf * extra end
	j.Transform = cf
end

local function setup(model)
	if rigs[model] or not model:IsA("Model") then return end
	local head = model:FindFirstChild("Head")
	local jaw = findBone(model, "Jaw")
	if not (head and jaw) then return end
	local upper = model:FindFirstChild("UpperTorso")
	local lower = model:FindFirstChild("LowerTorso")
	local neck = head:FindFirstChild("Neck") or model:FindFirstChild("Neck", true)
	local waist = upper and (upper:FindFirstChild("Waist") or model:FindFirstChild("Waist", true))
	local eyeL, eyeR = findBone(model, "LeftEye"), findBone(model, "RightEye")
	local hat = findBone(model, "HatBone")
	local eyesPart = model:FindFirstChild("Eyes", true)

	-- оси лица в системе головы (снимаем один раз, в покое)
	local hcf = head.CFrame
	local lateral = (eyeL and eyeR) and (eyeL.WorldPosition - eyeR.WorldPosition).Unit or hcf.RightVector
	local eyesMid = (eyeL and eyeR) and (eyeL.WorldPosition + eyeR.WorldPosition) / 2 or head.Position
	local faceN = eyesPart and (eyesPart.Position - eyesMid) or hcf.LookVector
	if faceN.Magnitude < 1e-3 then faceN = hcf.LookVector end
	faceN = (faceN - lateral * faceN:Dot(lateral)).Unit
	local up = faceN:Cross(lateral).Unit
	if up:Dot(hcf.UpVector) < 0 then up = -up end

	-- знак открывания рта: передняя точка челюсти должна уходить ОТ глаз
	local hinge = jaw:IsA("Bone") and jaw.WorldPosition or restFrame(jaw).Position
	local probe = hinge + faceN * 1.0
	local function rotAround(p, axis, a)
		return CFrame.new(hinge) * CFrame.fromAxisAngle(axis, a) * CFrame.new(-hinge) * p
	end
	local jawSign = ((rotAround(probe, lateral, 0.3) - eyesMid).Magnitude >
		(rotAround(probe, lateral, -0.3) - eyesMid).Magnitude) and 1 or -1

	local r = {
		model = model, head = head, upper = upper, lower = lower, jaw = jaw, eyeL = eyeL, eyeR = eyeR, hat = hat,
		eyes = eyesPart, neck = neck, waist = waist,
		neckC0 = neck and neck.C0, waistC0 = waist and waist.C0,
		latH = hcf:VectorToObjectSpace(lateral), nH = hcf:VectorToObjectSpace(faceN), upH = hcf:VectorToObjectSpace(up),
		jawSign = jawSign,
		jawOpen = 0, headRot = CFrame.new(), roll = 0, rollTarget = 0,
		nextScream = os.clock() + rand(CFG.SCREAM_EVERY), screamUntil = 0,
		nextTwitch = os.clock() + rand(CFG.TWITCH_EVERY),
		nextBlink = os.clock() + rand(CFG.BLINK_EVERY), blinkUntil = 0,
		sound = nil,
	}
	if neck then
		local jw = neck.Part0.CFrame * neck.C0
		r.nJoint = jw:VectorToObjectSpace(faceN)
	end
	if waist then
		r.latWaist = (waist.Part0.CFrame * waist.C0):VectorToObjectSpace(lateral)
	end
	if eyesPart then
		eyesPart.Material = Enum.Material.Neon
		eyesPart.Color = CFG.EYE_COLOR
	end
	if CFG.SCREAM_SOUND ~= "" then
		local s = Instance.new("Sound")
		s.SoundId, s.Volume, s.RollOffMaxDistance = CFG.SCREAM_SOUND, 1, 80
		s.Parent = head
		r.sound = s
	end
	rigs[model] = r
end

local function targetPos()
	local ch = player.Character
	local h = ch and (ch:FindFirstChild("Head") or ch:FindFirstChild("HumanoidRootPart"))
	return h and h.Position
end

local function step(r, t, dt)
	local head = r.head
	if not head.Parent then rigs[r.model] = nil return end
	local hcf = head.CFrame
	local lateral = hcf:VectorToWorldSpace(r.latH)
	local faceN = hcf:VectorToWorldSpace(r.nH)
	local up = hcf:VectorToWorldSpace(r.upH)
	local tp = targetPos()
	local dist = tp and (tp - head.Position).Magnitude or math.huge
	local sees = dist < CFG.LOOK_RADIUS
	local near = dist < CFG.NEAR_RADIUS
	local k = function(speed) return 1 - math.exp(-dt * speed) end

	-- крик
	local screaming = t < r.screamUntil
	if sees and t > r.nextScream then
		r.screamUntil = t + CFG.SCREAM_TIME
		r.nextScream = t + rand(CFG.SCREAM_EVERY)
		screaming = true
		if r.sound then r.sound:Play() end
	end

	-- челюсть
	local open
	if screaming then
		open = 1.0
	elseif near then
		open = 0.12 + 0.14 * math.abs(math.sin(t * 15))           -- щёлкает зубами
	else
		open = 0.05 + 0.04 * math.sin(t * 1.6)                    -- дышит
	end
	r.jawOpen += (open - r.jawOpen) * k(screaming and 22 or 12)
	setRot(r.jaw, lateral, r.jawSign * r.jawOpen * CFG.JAW_MAX)

	-- голова: смотрит на игрока + резкие наклоны набок
	if r.neck and r.nJoint then
		if t > r.nextTwitch then
			r.nextTwitch = t + rand(CFG.TWITCH_EVERY)
			r.rollTarget = (rng:NextNumber() < 0.5 and -1 or 1) * rng:NextNumber(math.rad(12), math.rad(35))
		end
		r.rollTarget *= (1 - k(0.6))                              -- медленно возвращается
		r.roll += (r.rollTarget - r.roll) * k(18)                  -- но наклоняется резко
		local jw = r.neck.Part0.CFrame * r.neckC0
		local want = CFrame.new()
		if sees then
			local dir = jw:VectorToObjectSpace(tp - jw.Position).Unit
			local axis = r.nJoint:Cross(dir)
			if axis.Magnitude > 1e-4 then
				local a = math.min(math.acos(math.clamp(r.nJoint:Dot(dir), -1, 1)), CFG.HEAD_MAX)
				if screaming then a = math.min(a * 1.15, CFG.HEAD_MAX) end
				want = CFrame.fromAxisAngle(axis.Unit, a)
			end
		end
		r.headRot = r.headRot:Lerp(want, k(screaming and 10 or 4))
		r.neck.C0 = r.neckC0 * r.headRot * CFrame.fromAxisAngle(r.nJoint, r.roll)
	end

	-- дыхание корпуса
	if r.waist and r.latWaist then
		r.waist.C0 = r.waistC0 * CFrame.fromAxisAngle(r.latWaist, 0.035 * math.sin(t * 1.6))
	end

	-- глаза: следят за игроком, «дрожат»
	for _, eye in ipairs({ r.eyeL, r.eyeR }) do
		if eye then
			local base = restFrame(eye)
			local a, axis = 0, lateral
			if sees then
				local dir = (tp - base.Position).Unit
				local ax = faceN:Cross(dir)
				if ax.Magnitude > 1e-4 then
					axis = ax.Unit
					a = math.min(math.acos(math.clamp(faceN:Dot(dir), -1, 1)), CFG.EYE_MAX)
				end
			end
			local jitter = CFrame.fromAxisAngle(Vector3.new(0, 1, 0), 0.01 * math.sin(t * 37 + eye.Name:len()))
			setRot(eye, axis, a, jitter)
		end
	end

	-- моргание и цвет глаз
	if r.eyes then
		if t > r.nextBlink then
			r.blinkUntil = t + 0.11
			r.nextBlink = t + rand(CFG.BLINK_EVERY)
			if rng:NextNumber() < 0.25 then r.nextBlink = t + 0.25 end   -- иногда двойное моргание
		end
		local target = screaming and CFG.EYE_SCREAM or CFG.EYE_COLOR
		r.eyeColor = (r.eyeColor or CFG.EYE_COLOR):Lerp(target, k(screaming and 20 or 5))
		if t < r.blinkUntil then                                   -- веки: глаз гаснет и становится цветом маски
			r.eyes.Material, r.eyes.Color = Enum.Material.SmoothPlastic, Color3.fromRGB(8, 7, 8)
		else
			r.eyes.Material, r.eyes.Color = Enum.Material.Neon, r.eyeColor
		end
	end

	-- фуражка: покачивается, при крике подпрыгивает
	if r.hat then
		local wob = 0.05 * math.sin(t * 2.3) + (screaming and 0.12 * math.sin(t * 40) or 0)
		local lift = screaming and 0.35 or 0
		local base = restFrame(r.hat)
		local liftLocal = base:VectorToObjectSpace(up) * lift
		r.hat.Transform = CFrame.new(liftLocal) * CFrame.fromAxisAngle(base:VectorToObjectSpace(lateral).Unit, wob)
	end
end

local function scan(root)
	for _, d in ipairs(root:GetDescendants()) do
		if d.Name == "Jaw" and (d:IsA("Bone") or d:IsA("Motor6D")) then
			local m = d:FindFirstAncestorOfClass("Model")
			if m then setup(m) end
		end
	end
end

scan(workspace)
workspace.DescendantAdded:Connect(function(d)
	if d.Name == "Jaw" then
		task.wait(0.5)
		local m = d:FindFirstAncestorOfClass("Model")
		if m then setup(m) end
	end
end)

RunService.RenderStepped:Connect(function(dt)
	local t = os.clock()
	for _, r in pairs(rigs) do
		step(r, t, dt)
	end
end)
