--[[
	Живое тело коридорного — LocalScript.
	Положи в StarterPlayer > StarterPlayerScripts. Работает для всех коридорных в Workspace
	(модель Bellhop_R15_Body: суставы R15 + кости пальцев и носков).

	Анимация процедурная (считается каждый кадр, ID анимаций не нужны):
	  * стоя — дышит, покачивается, плечи и руки «висят» с запаздыванием, пальцы шевелятся,
	    иногда перебирают по очереди или резко дёргаются, корпус время от времени «хрустит» рывком;
	  * при ходьбе — сутулая раскачивающаяся походка: шаг с подъёмом колена, перекат стопы и носка,
	    качание таза, противоход длинных рук, болтающиеся кисти;
	  * при беге — наклон вперёд, руки тянутся вперёд, когти щёлкают;
	  * рядом с игроком — тянется к нему обеими руками и сжимает-разжимает когти, голова следит.
	Лицо (челюсть, глаза, фуражка) НЕ анимируется.

	Настройки — таблица CFG. Обычные анимации (Animator) для этой модели не нужны:
	BellhopNPC.server.lua только водит коридорного, всё движение тела делает этот скрипт.
]]

local Players = game:GetService("Players")
local RunService = game:GetService("RunService")
local player = Players.LocalPlayer

local CFG = {
	STRIDE = 6.5,              -- длина шага (стады за цикл) — меньше = чаще шаги
	REACH_RADIUS = 11,         -- ближе — тянется к игроку и хватает
	LOOK_RADIUS = 40,          -- голова следит за игроком (0 — не следит)
	HEAD_MAX = math.rad(35),
	TWITCH_EVERY = { 5, 11 },  -- «хруст» корпуса
	FINGER_WAVE_EVERY = { 3, 7 },
	AMOUNT = 1.0,              -- общая сила всех движений (0.5 — спокойнее, 1.5 — дёрганее)
}

local rigs = {}
local rng = Random.new()
local TAU = math.pi * 2

local function rand(r) return rng:NextNumber(r[1], r[2]) end
local function clamp01(x) return math.clamp(x, 0, 1) end
local function bump(x, w)                 -- короткий импульс около x=0 ширины w
	return math.exp(-(x / w) ^ 2)
end

-- ---------------------------------------------------------------- суставы
local function joint(model, name)
	for _, d in ipairs(model:GetDescendants()) do
		if d:IsA("Motor6D") and d.Name == name then
			return { m = d, rest = d.Part0.CFrame * d.C0 }
		end
	end
	return nil
end

-- знак поворота: при +угле точка probe должна смещаться по want
local function sign(pivot, axisW, probe, want)
	local cf = CFrame.new(pivot) * CFrame.fromAxisAngle(axisW, 0.3) * CFrame.new(-pivot)
	return ((cf * probe) - probe):Dot(want) >= 0 and 1 or -1
end

local function calibJoint(j, axisW, probe, want)
	if not j then return nil end
	return { axis = j.rest:VectorToObjectSpace(axisW).Unit, s = sign(j.rest.Position, axisW, probe, want) }
end

local function setup(model)
	if rigs[model] or not model:IsA("Model") then return end
	local hrp = model:FindFirstChild("HumanoidRootPart")
	local head = model:FindFirstChild("Head")
	if not (hrp and head) then return end
	local P = function(n) return model:FindFirstChild(n) end
	local R, F, U = hrp.CFrame.RightVector, hrp.CFrame.LookVector, hrp.CFrame.UpVector

	local r = { model = model, hrp = hrp, head = head, j = {}, ax = {}, fingers = {}, toes = {} }
	local J = r.j
	for _, n in ipairs({ "Root", "Waist", "Neck", "LeftShoulder", "RightShoulder", "LeftElbow", "RightElbow",
		"LeftWrist", "RightWrist", "LeftHip", "RightHip", "LeftKnee", "RightKnee", "LeftAnkle", "RightAnkle" }) do
		J[n] = joint(model, n)
	end
	if not (J.Root and J.LeftHip and J.LeftShoulder) then return end
	local A = r.ax
	local headP = head.Position
	local faceP = headP + F * 1.5
	-- корпус
	A.rootLean = calibJoint(J.Root, R, headP, F)
	A.rootSway = calibJoint(J.Root, F, headP, R)
	A.rootTwist = calibJoint(J.Root, U, faceP, R)
	A.rootUp = J.Root and J.Root.rest:VectorToObjectSpace(U)
	A.waistLean = calibJoint(J.Waist, R, headP, F)
	A.waistSway = calibJoint(J.Waist, F, headP, R)
	A.waistTwist = calibJoint(J.Waist, U, faceP, R)
	A.neckNod = calibJoint(J.Neck, R, faceP, -U)
	A.neckTurn = calibJoint(J.Neck, U, faceP, R)
	A.neckTilt = calibJoint(J.Neck, F, headP + U, R)
	-- руки и ноги
	for _, side in ipairs({ "Left", "Right" }) do
		local out = (side == "Right") and R or -R
		local hand, foot, lower = P(side .. "Hand"), P(side .. "Foot"), P(side .. "LowerArm")
		if hand and lower then
			local tip = hand.Position + (hand.Position - lower.Position).Unit * 1.0
			A[side .. "ShSwing"] = calibJoint(J[side .. "Shoulder"], R, hand.Position, F)
			A[side .. "ShOut"] = calibJoint(J[side .. "Shoulder"], F, hand.Position, out)
			A[side .. "ShTwist"] = calibJoint(J[side .. "Shoulder"], U, hand.Position, F)
			A[side .. "Elbow"] = calibJoint(J[side .. "Elbow"], R, hand.Position, F)
			A[side .. "Wrist"] = calibJoint(J[side .. "Wrist"], R, tip, F)
		end
		if foot then
			local toeP = foot.Position + F * 0.8
			A[side .. "HipSwing"] = calibJoint(J[side .. "Hip"], R, foot.Position, F)
			A[side .. "HipOut"] = calibJoint(J[side .. "Hip"], F, foot.Position, out)
			A[side .. "Knee"] = calibJoint(J[side .. "Knee"], R, foot.Position, -F)
			A[side .. "Ankle"] = calibJoint(J[side .. "Ankle"], R, toeP, U)
		end
		-- пальцы: цепочки костей {Side}Finger{N}_{1..3}
		local chains = {}
		for _, d in ipairs(model:GetDescendants()) do
			if d:IsA("Bone") then
				local s2, fi, k = d.Name:match("^(%a+)Finger(%d+)_(%d)$")
				if s2 == side then
					fi, k = tonumber(fi), tonumber(k)
					chains[fi] = chains[fi] or {}
					chains[fi][k] = d
				end
			end
		end
		local palm = Vector3.zero
		for _, ch in pairs(chains) do
			if ch[1] and ch[2] and ch[3] then
				palm = palm + ((ch[1].WorldPosition + ch[3].WorldPosition) / 2 - ch[2].WorldPosition)
			end
		end
		if palm.Magnitude > 1e-4 then
			palm = palm.Unit
			local list = {}
			for fi, ch in pairs(chains) do
				if ch[1] and ch[2] and ch[3] then
					local bones = {}
					for k = 1, 3 do
						local b = ch[k]
						local nxt = ch[k + 1] or nil
						local dir = nxt and (nxt.WorldPosition - b.WorldPosition) or (ch[3].WorldPosition - ch[2].WorldPosition)
						local axW = dir:Cross(palm)
						if axW.Magnitude < 1e-5 then axW = R end
						local wcf = b.WorldCFrame
						bones[k] = { b = b, curl = wcf:VectorToObjectSpace(axW.Unit), spread = wcf:VectorToObjectSpace(palm) }
					end
					table.insert(list, { i = fi, bones = bones, twitch = 0, nextTwitch = os.clock() + rng:NextNumber(1, 6) })
				end
			end
			table.sort(list, function(a, b) return a.i < b.i end)
			r.fingers[side] = list
		end
		local toe = model:FindFirstChild(side .. "Toe", true)
		if toe and toe:IsA("Bone") then
			local wcf = toe.WorldCFrame
			local probe = toe.WorldPosition + F * 0.5
			r.toes[side] = { b = toe, axis = wcf:VectorToObjectSpace(R), s = sign(toe.WorldPosition, R, probe, U) }
		end
	end

	r.phase, r.walkW, r.runW, r.reachW = 0, 0, 0, 0
	r.headRot = CFrame.new()
	r.crack, r.nextCrack, r.crackAxis = 0, os.clock() + rand(CFG.TWITCH_EVERY), 1
	r.waveT, r.nextWave = -10, os.clock() + rand(CFG.FINGER_WAVE_EVERY)
	r.seed = rng:NextNumber(0, 100)
	rigs[model] = r
end

-- ---------------------------------------------------------------- применение поворотов
local function rotOf(c, a)
	if not c or a == 0 then return CFrame.new() end
	return CFrame.fromAxisAngle(c.axis, c.s * a * CFG.AMOUNT)
end

local function apply(j, ...)
	if not j then return end
	local cf = CFrame.new()
	for _, pair in ipairs({ ... }) do
		cf = cf * rotOf(pair[1], pair[2])
	end
	j.m.Transform = cf
end

local function targetPos()
	local ch = player.Character
	local h = ch and (ch:FindFirstChild("Head") or ch:FindFirstChild("HumanoidRootPart"))
	return h and h.Position
end

local function step(r, t, dt)
	if not r.hrp.Parent then rigs[r.model] = nil return end
	local J, A = r.j, r.ax
	local k = function(speed) return 1 - math.exp(-dt * speed) end
	local v = r.hrp.AssemblyLinearVelocity
	local speed = Vector3.new(v.X, 0, v.Z).Magnitude
	r.walkW = r.walkW + (clamp01(speed / 5) - r.walkW) * k(5)
	r.runW = r.runW + (clamp01((speed - 11) / 7) - r.runW) * k(4)
	r.phase = (r.phase + dt * speed / CFG.STRIDE * TAU) % TAU
	local tp = targetPos()
	local dist = tp and (tp - r.head.Position).Magnitude or math.huge
	r.reachW = r.reachW + (((dist < CFG.REACH_RADIUS) and 1 or 0) - r.reachW) * k(4)
	local w, run, reach = r.walkW, r.runW, r.reachW
	local idle = 1 - w
	local ph = r.phase
	local s0 = r.seed
	local breath = math.sin(t * 1.4 + s0)

	-- резкий «хруст» корпуса
	if t > r.nextCrack then
		r.nextCrack = t + rand(CFG.TWITCH_EVERY)
		r.crack = 1
		r.crackAxis = rng:NextNumber() < 0.5 and -1 or 1
	end
	r.crack = r.crack * (1 - k(7))
	local crack = r.crack * r.crackAxis

	-- ---------- корпус
	local bob = -0.22 * math.abs(math.sin(ph)) * w
	local lean = 0.06 * breath * idle + (0.14 + 0.25 * run) * w + 0.12 * reach
	if J.Root then
		local cf = CFrame.new(A.rootUp * bob)
			* rotOf(A.rootLean, lean * 0.5)
			* rotOf(A.rootSway, 0.04 * math.sin(t * 0.55 + s0) * idle + 0.09 * math.sin(ph) * w)
			* rotOf(A.rootTwist, 0.05 * math.sin(t * 0.37 + s0) * idle + 0.14 * math.sin(ph) * w)
		J.Root.m.Transform = cf
	end
	apply(J.Waist,
		{ A.waistLean, lean * 0.6 + 0.03 * breath },
		{ A.waistSway, 0.03 * math.sin(t * 0.8 + s0) * idle + 0.18 * crack },
		{ A.waistTwist, -0.17 * math.sin(ph) * w + 0.04 * math.sin(t * 0.5) * idle })

	-- ---------- голова (тело: качается с шагом, следит за игроком — не мимика)
	if J.Neck then
		local want = CFrame.new()
		if CFG.LOOK_RADIUS > 0 and dist < CFG.LOOK_RADIUS then
			local jw = J.Neck.m.Part0.CFrame * J.Neck.m.C0
			local fwd = jw:VectorToObjectSpace(r.hrp.CFrame.LookVector)
			local dir = jw:VectorToObjectSpace(tp - jw.Position).Unit
			local ax = fwd:Cross(dir)
			if ax.Magnitude > 1e-4 then
				want = CFrame.fromAxisAngle(ax.Unit, math.min(math.acos(math.clamp(fwd:Dot(dir), -1, 1)), CFG.HEAD_MAX))
			end
		end
		r.headRot = r.headRot:Lerp(want, k(3))
		J.Neck.m.Transform = r.headRot
			* rotOf(A.neckNod, -0.07 * math.sin(2 * ph) * w + 0.03 * breath * idle - lean * 0.3)
			* rotOf(A.neckTilt, 0.05 * math.sin(t * 0.45 + s0) * idle - 0.3 * crack)
	end

	-- ---------- ноги: шаг, подъём колена, перекат стопы и носка
	for i, side in ipairs({ "Left", "Right" }) do
		local p = ph + (i == 2 and math.pi or 0)
		local swing = (0.42 + 0.18 * run) * math.sin(p) * w
		local knee = (0.12 + (0.72 + 0.3 * run) * math.max(0, math.sin(p + 1.7))) * w + 0.06 * idle * (1 + 0.5 * breath)
		local ankle = (-0.3 * math.sin(p) + 0.25 * math.max(0, math.sin(p + 1.7))) * w
		apply(J[side .. "Hip"], { A[side .. "HipSwing"], swing - 0.05 * idle },
			{ A[side .. "HipOut"], 0.05 * w + 0.02 * idle })
		apply(J[side .. "Knee"], { A[side .. "Knee"], knee })
		apply(J[side .. "Ankle"], { A[side .. "Ankle"], ankle })
		local toe = r.toes[side]
		if toe then
			local a = 0.55 * math.max(0, -math.sin(p - 0.5)) * w                -- толчок носком
			toe.b.Transform = CFrame.fromAxisAngle(toe.axis, toe.s * a * CFG.AMOUNT)
		end
	end

	-- ---------- руки: висят с запаздыванием / противоход / тянутся к игроку
	for i, side in ipairs({ "Left", "Right" }) do
		local p = ph + (i == 1 and math.pi or 0) - 0.4                          -- противоход ногам
		local lag = math.sin(t * 0.9 + i * 1.3 + s0)
		local swing = (0.05 * lag) * idle + (0.55 * math.sin(p)) * w * (1 - run) + (0.9 + 0.3 * math.sin(p)) * run
		swing = swing * (1 - reach) + 1.15 * reach
		local out = 0.04 + 0.02 * lag * idle + 0.08 * w + 0.18 * reach
		local twist = 0.1 * crack * (i == 1 and 1 or -1)
		local elbow = (0.18 + 0.05 * math.sin(t * 1.1 + i)) * idle + (0.25 + 0.35 * math.max(0, math.sin(p + 0.6))) * w * (1 - run)
			+ 0.15 * run
		elbow = elbow * (1 - reach) + 0.25 * reach
		local wrist = 0.06 * math.sin(t * 1.3 + i * 2) * idle + 0.2 * math.sin(p - 0.8) * w - 0.25 * reach
		apply(J[side .. "Shoulder"], { A[side .. "ShSwing"], swing }, { A[side .. "ShOut"], out },
			{ A[side .. "ShTwist"], twist })
		apply(J[side .. "Elbow"], { A[side .. "Elbow"], elbow })
		apply(J[side .. "Wrist"], { A[side .. "Wrist"], wrist })

		-- пальцы
		local list = r.fingers[side]
		if list then
			if t > r.nextWave then
				r.nextWave = t + rand(CFG.FINGER_WAVE_EVERY)
				r.waveT = t
			end
			local n = #list
			for fi, f in ipairs(list) do
				if t > f.nextTwitch then
					f.nextTwitch = t + rng:NextNumber(1.5, 6)
					f.twitch = rng:NextNumber(0.3, 0.7) * (rng:NextNumber() < 0.5 and -0.6 or 1)
				end
				f.twitch = f.twitch * (1 - k(9))
				local x = fi / n
				local curl = 0.18 + 0.12 * math.sin(t * 0.8 + fi * 1.7 + s0) * idle            -- медленное шевеление
					+ 0.6 * bump(t - r.waveT - x * 0.5, 0.12) * idle                             -- перебор по очереди
					+ f.twitch
					+ (0.15 * math.sin(p * 2 + fi)) * w
					+ (0.45 * math.max(0, math.sin(t * 7 + fi * 0.7))) * run                     -- щёлкает когтями
				local grab = 0.5 + 0.5 * math.sin(t * 5 - x * 2.5)                                -- сжать-разжать
				curl = curl * (1 - reach) + (-0.35 + 1.1 * grab ^ 2) * reach
				local spread = (x - 0.5) * (0.15 + 0.3 * reach * (1 - grab))
				for kk, bn in ipairs(f.bones) do
					local share = (kk == 1) and 0.8 or 1.1
					bn.b.Transform = CFrame.fromAxisAngle(bn.curl, curl * share * CFG.AMOUNT)
						* ((kk == 1) and CFrame.fromAxisAngle(bn.spread, spread * CFG.AMOUNT) or CFrame.new())
				end
			end
		end
	end
end

local function scan(root)
	for _, d in ipairs(root:GetDescendants()) do
		if d:IsA("Bone") and d.Name:match("Finger%d+_1$") then
			local m = d:FindFirstAncestorOfClass("Model")
			if m then setup(m) end
		end
	end
end

scan(workspace)
workspace.DescendantAdded:Connect(function(d)
	if d:IsA("Bone") and d.Name:match("Finger%d+_1$") then
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
