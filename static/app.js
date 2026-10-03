        // --- 1. ОПЦИОНАЛЬНЫЙ ФУНКЦИОНАЛ КОНСОЛИ ---
        const chatContainer = document.getElementById('chatContainer');
        const userInput = document.getElementById('userInput');
        const sendBtn = document.getElementById('sendBtn');
        const micToggle = document.getElementById('micToggle');
        const audioPlayer = document.getElementById('audioPlayer');

        let isStreaming = false, audioContext, analyser, microphone, stream, mediaRecorder = null, audioChunks = [], silenceTimer = null;
        let isSpeaking = false, isProcessingAI = false, isAudioPlaying = false;
        const THRESHOLD = 8, SILENCE_TIMEOUT = 300; let lastUserMsg = null, lastAIMsg = null;

        function addMessage(text, sender, extraClass = '') {
            const msg = document.createElement('div'); msg.className = `message ${sender} ${extraClass}`; msg.innerText = text;
            chatContainer.appendChild(msg); chatContainer.scrollTop = chatContainer.scrollHeight; return msg;
        }

        function stopAudio() {
            if (!audioPlayer.paused) { audioPlayer.pause(); audioPlayer.currentTime = 0; isAudioPlaying = false; document.querySelectorAll('.play-audio-btn').forEach(btn => { btn.innerHTML = 'ПРОСЛУШАТЬ'; }); }
        }

        async function toggleAlwaysListening() {
            if (!isStreaming) {
                try {
                    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                    audioContext = new(window.AudioContext || window.webkitAudioContext)();
                    if (audioContext.state === 'suspended') await audioContext.resume();
                    microphone = audioContext.createMediaStreamSource(stream); analyser = audioContext.createAnalyser(); analyser.fftSize = 512;
                    microphone.connect(analyser); isStreaming = true;
                    micToggle.classList.add('active'); micToggle.innerText = '⏺'; startVADListener();
                } catch (err) { alert('Ошибка микрофона: ' + err.message); }
            } else {
                isStreaming = false; micToggle.classList.remove('active'); micToggle.innerText = '🎙'; clearTimeout(silenceTimer);
                if (mediaRecorder && mediaRecorder.state !== 'inactive') mediaRecorder.stop();
                if (stream) stream.getTracks().forEach(t => t.stop()); if (audioContext) audioContext.close();
            }
        }

        function startVADListener() {
            if (!isStreaming) return; const dataArray = new Uint8Array(analyser.frequencyBinCount);
            function analyze() {
                if (!isStreaming) return; analyser.getByteFrequencyData(dataArray); let sumSquares = 0;
                for (let i = 0; i < dataArray.length; i++) sumSquares += dataArray[i] * dataArray[i];
                const rms = Math.sqrt(sumSquares / dataArray.length);
                if (rms > THRESHOLD && !isProcessingAI) {
                    if (!isSpeaking) { isSpeaking = true; startChunkRecording(); }
                    clearTimeout(silenceTimer); silenceTimer = setTimeout(() => { if (isSpeaking) { isSpeaking = false; stopAndSendChunk(); } }, SILENCE_TIMEOUT);
                }
                requestAnimationFrame(analyze);
            } analyze();
        }

        function startChunkRecording() {
            try {
                let options = {};
                if (MediaRecorder.isTypeSupported('audio/webm')) options = { mimeType: 'audio/webm' }; else if (MediaRecorder.isTypeSupported('audio/mp4')) options = { mimeType: 'audio/mp4' };
                mediaRecorder = new MediaRecorder(stream, options); audioChunks = [];
                mediaRecorder.ondataavailable = e => { if (e.data.size > 0) audioChunks.push(e.data); }; mediaRecorder.start();
            } catch (e) {}
        }

        function stopAndSendChunk() {
            if (mediaRecorder && mediaRecorder.state !== 'inactive') {
                mediaRecorder.onstop = async () => { if (audioChunks.length > 0) await transmitAudioToServer(new Blob(audioChunks, { type: mediaRecorder.mimeType || 'audio/webm' })); };
                mediaRecorder.stop();
            }
        }

        async function transmitAudioToServer(blob) {
            if (isProcessingAI) return; isProcessingAI = true; hideScreensaver();
            if (!lastUserMsg || lastUserMsg.className.indexOf('user') === -1) lastUserMsg = addMessage('...', 'user');
            if (!lastAIMsg || lastAIMsg.className.indexOf('ai') === -1) lastAIMsg = addMessage('...', 'ai');
            const formData = new FormData(); formData.append('file', blob, 's.webm');

            try {
                const res = await fetch('/api/voice', { method: 'POST', body: formData }); if (!res.ok) throw new Error('NET FAULT');
                const data = await res.json();
                if (data.status === 'stop_audio' || data.status === 'ignored') { if(data.status==='stop_audio') stopAudio(); lastUserMsg?.remove(); lastAIMsg?.remove(); lastUserMsg = null; lastAIMsg = null; return; }
                lastUserMsg.innerText = '🎙 : ' + data.user_text; lastAIMsg.innerText = data.response; if (data.play_audio) appendPlayButton(lastAIMsg);
            } catch (err) { lastAIMsg.innerText = '⚠️ ' + err.message; }
            finally { isProcessingAI = false; lastUserMsg = null; lastAIMsg = null; }
        }

        async function appendPlayButton(msgContainer) {
            const btn = document.createElement('button'); btn.className = 'play-audio-btn'; btn.innerHTML = 'DL...'; btn.disabled = true;
            msgContainer.appendChild(document.createElement('br')); msgContainer.appendChild(btn); msgContainer.scrollIntoView({ block: 'nearest' });
            try {
                const res = await fetch('/api/audio?t=' + Date.now()); if (!res.ok) throw new Error();
                audioPlayer.src = URL.createObjectURL(await res.blob());
                btn.innerHTML = '🔊 ОТВЕТ'; btn.disabled = false;
                btn.onclick = () => {
                    if (!audioPlayer.paused) { audioPlayer.pause(); audioPlayer.currentTime = 0; isAudioPlaying = false; btn.innerHTML = '🔊 ОТВЕТ'; return; }
                    audioPlayer.currentTime = 0; audioPlayer.play().catch(e=>0); isAudioPlaying = true; btn.innerHTML = '⏸ СТОП';
                };
                audioPlayer.play().then(() => { isAudioPlaying = true; btn.innerHTML = '⏸ СТОП'; }).catch(() => 0);
                audioPlayer.onended = () => { isAudioPlaying = false; document.querySelectorAll('.play-audio-btn').forEach(b => b.innerHTML = '🔊 ОТВЕТ'); };
            } catch (err) { btn.innerHTML = 'ERROR'; }
        }

        async function sendMessage() {
            const text = userInput.value.trim(); if (!text) return; hideScreensaver();
            if (text.startsWith('/')) {
                userInput.value = ''; const sysMsg = addMessage(`SYS: ${text}`, 'system');
                try {
                    const res = await fetch('/api/command', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ cmd: text }) });
                    sysMsg.innerText = (await res.json()).output;
                } catch (err) { sysMsg.innerText = 'ERR: ' + err.message; } return;
            }
            addMessage(text, 'user'); userInput.value = ''; isProcessingAI = true; const aiMsg = addMessage('Чтение логов...', 'ai');
            try {
                const res = await fetch('/api/ask', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text }) });
                const data = await res.json(); aiMsg.innerText = data.response; if (data.play_audio) appendPlayButton(aiMsg);
            } catch (err) { aiMsg.innerText = 'FAIL: ' + err.message; } finally { isProcessingAI = false; }
        }
        function handleKey(e) { if (e.key === 'Enter') sendMessage(); }


        // --- 2. THE QUANTUM J.A.R.V.I.S RENDER ENGINE v3.0 (SACRED TECH) --- //
        let idTimeT = null; const S_SLEEP_DELAY = 5000; let showCore = false;
        let SCE, CM, RDR, CTROLS, UNI_GRP, UPDATERS = [], sysFrame = null; 
        let engineInst = false;
        
        const CLRS = {
            Cyantific: 0x00f3ff, // Научный ярко-лазурный 
            HotGold: 0xffb700,   // Теплый сочный янтарь (Основной UI Тони)
            BurnOrange: 0xff3800,// Техногенный плазменный кроваво-красный в основе
            DiamondPt: 0xfffcf0 // Сияние
        };

        function invokeScreensaverOverlay() {
            if (showCore) return; showCore = true;
            document.getElementById('screensaver-ui').classList.add('active');
            document.activeElement?.blur();
            if (!engineInst) setupMasterGeometricHologram();
            sysFrame = requestAnimationFrame(jarvisLoopProc);
        }

        function hideScreensaver() {
            if (!showCore) return; showCore = false;
            document.getElementById('screensaver-ui').classList.remove('active');
            clearTimeout(idTimeT); idTimeT = setTimeout(invokeScreensaverOverlay, S_SLEEP_DELAY);
            userInput.focus();
            if(sysFrame) cancelAnimationFrame(sysFrame); 
        }

        function checkTouchLive() { if (!showCore) { clearTimeout(idTimeT); idTimeT = setTimeout(invokeScreensaverOverlay, S_SLEEP_DELAY); } }
        window.addEventListener('load', () => {
            userInput.focus();
            ['mousemove','mousedown','keydown','scroll','touchstart','wheel'].forEach(evt => document.addEventListener(evt, checkTouchLive, {passive: true}));
            checkTouchLive();
        });


        // СОЗДАЕМ ПОЛНУЮ МАГИЮ СЛОЖНЫХ, ЭСТЕТИЧНЫХ ПРОЦЕДУРНЫХ ФОРМ (Никаких плохих линий, только четкость!)
        function setupMasterGeometricHologram() {
            if(typeof THREE === 'undefined') return;
            const cnvDiv = document.getElementById('three-canvas-container');

            // 1. Scene & Atmosphere (Среда глубины для растворения осей по Z/Y)
            SCE = new THREE.Scene();
            SCE.fog = new THREE.FogExp2(0x050104, 0.018); 

            CM = new THREE.PerspectiveCamera(40, window.innerWidth/window.innerHeight, 0.5, 200);
            CM.position.z = 24; 

            // 2. Additive Rendering engine for HDR looks on mobile devices
            RDR = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: "high-performance" });
            RDR.setPixelRatio(Math.min(window.devicePixelRatio, 2));
            RDR.setSize(window.innerWidth, window.innerHeight);
            cnvDiv.appendChild(RDR.domElement);

            // Orbit Interactor
            CTROLS = new THREE.OrbitControls(CM, RDR.domElement);
            CTROLS.enableDamping = true; CTROLS.dampingFactor = 0.035; CTROLS.enablePan = false;
            CTROLS.minDistance = 6; CTROLS.maxDistance = 60;
            window.addEventListener('resize', () => { if(CM) { CM.aspect=window.innerWidth/window.innerHeight; CM.updateProjectionMatrix(); RDR.setSize(window.innerWidth,window.innerHeight); } });

            UNI_GRP = new THREE.Group(); SCE.add(UNI_GRP);
            UPDATERS = [];
            const OvrBld = { transparent: true, blending: THREE.AdditiveBlending, depthWrite: false };

            // Материалы колец — для перекраски по состоянию ЛУЧА
            const holoRings = [];

            // ----- КОМПОНЕНТ 1: QUANTUM DIAMOND CORE (Священная Геометрия: Взаимопроникающие Октаэдр, Икосаэдр и Додекаэдр) -----
            const cHeart = new THREE.Group();
            
            // Внутренний сплошной циановый кристаллик, как мозг данных.
            const bMatDia = new THREE.MeshBasicMaterial({color: CLRS.Cyantific, opacity: 0.1, ...OvrBld});
            let coreDia = new THREE.Mesh(new THREE.OctahedronGeometry(1.0, 0), bMatDia);
            
            // Закованный в перекрещенный каркас Додекаэдра.
            const wGold = new THREE.LineBasicMaterial({color: CLRS.HotGold, opacity: 0.2, ...OvrBld});
            let cageDodeca1 = new THREE.LineSegments(new THREE.WireframeGeometry(new THREE.DodecahedronGeometry(2.5, 0)), wGold);
            let cageIcosa1 = new THREE.LineSegments(new THREE.WireframeGeometry(new THREE.IcosahedronGeometry(2.8, 1)), new THREE.LineBasicMaterial({color: CLRS.DiamondPt, opacity:0.12, ...OvrBld}));
            
            // Коронное огненное облако вокруг платины ядра.
            const pFGeom = new THREE.BufferGeometry();
            const pfLgth = 700; const pfArr = new Float32Array(pfLgth*3);
            for (let e=0; e<pfLgth; e++){
                let rp = 1.4 + 1.2*Math.pow(Math.random(),2);
                let xTh = 2*Math.PI*Math.random(); let yPh = Math.acos(2*Math.random()-1);
                pfArr[e*3] = rp*Math.sin(yPh)*Math.cos(xTh); pfArr[e*3+1] = rp*Math.sin(yPh)*Math.sin(xTh); pfArr[e*3+2] = rp*Math.cos(yPh);
            }
            pFGeom.setAttribute('position', new THREE.BufferAttribute(pfArr, 3));
            let coreFire = new THREE.Points(pFGeom, new THREE.PointsMaterial({color:CLRS.BurnOrange, size:0.045, ...OvrBld, opacity: 0.7}));

            cHeart.add(coreDia, cageDodeca1, cageIcosa1, coreFire);
            
            // Закинем все гео-капсулы сердца в функцию анимации через хуки userData.
            cageDodeca1.userData = { ry: 0.003, rx: 0.001 }; cageIcosa1.userData = { ry: -0.0015, rx: -0.002 }; coreDia.userData = { ry: -0.008 };
            UPDATERS.push(cageDodeca1, cageIcosa1, coreDia);
            UNI_GRP.add(cHeart);


            // ----- КОМПОНЕНТ 2: МАГИСТРАЛЬ СКОРОСТИ ГЕКСАГОНОВ (Hex Vertical Matrix Corridors) -----
            // Мы выстраиваем несколько длинных призрачных проволочных шестиугольников с обдувающимися концами для создания "Матрицы Баз Данных", уходящих вверх/вниз
            for (let idxCol=1; idxCol<=3; idxCol++){
                let radBase = 1.8 + idxCol * 0.4;
                let c_ht = 18.0 + (idxCol * 6.0); // очень высокие цилиндры
                // Строим с radiusSegments=6 = идеальный Хексагон! (Пчёлинная сота/Вычислительный шлейф).
                let hCylG = new THREE.WireframeGeometry(new THREE.CylinderGeometry(radBase, radBase, c_ht, 6, 4, true));
                // Понижаем прозрачность очень сильно (0.04), чтобы матричный эффект был тонким призраком. 
                let mtxLn = new THREE.LineSegments(hCylG, new THREE.LineBasicMaterial({color: CLRS.Cyantific, ...OvrBld, opacity:0.025 + (Math.random()*0.02)}));
                // Чутка повернуть вокруг центра:
                mtxLn.rotation.y = Math.PI / idxCol; 
                mtxLn.userData = {ry: (idxCol%2===0?-1:1)*0.002}; // Разное вращение
                UNI_GRP.add(mtxLn);
                UPDATERS.push(mtxLn);
            }


            // ----- КОМПОНЕНТ 3: ЗОНЫ РАДАРА ТЕЛЕМЕТРИИ (Рассекающие Проекционные Конусы шлема Iron Man) -----
            const bConeMats = new THREE.LineBasicMaterial({ color: CLRS.BurnOrange, opacity: 0.04, ...OvrBld });
            let upCone = new THREE.LineSegments(new THREE.WireframeGeometry(new THREE.ConeGeometry(5, 7, 36, 1, true)), bConeMats);
            let dnCone = new THREE.LineSegments(new THREE.WireframeGeometry(new THREE.ConeGeometry(5, 7, 36, 1, true)), bConeMats);
            upCone.position.y = -6.5; // опущены, так что острие смотрит кверху? Конструкция перевертышей.
            dnCone.position.y = 6.5;
            dnCone.rotation.z = Math.PI; // Свести носики друг на друга? Наоборот, базы друг к другу как рупоры!
            upCone.userData={ry:0.002}; dnCone.userData={ry:-0.002}; 
            UNI_GRP.add(upCone, dnCone);
            UPDATERS.push(upCone, dnCone);


            // ----- КОМПОНЕНТ 4: ВИРТУАЛЬНЫЕ УЗЛЫ-ИССЛЕДОВАТЕЛИ & КАРУСЕЛЬ РЕЖЕКТОРНЫХ ШКАЛ HUD -----
            // Сгенерирует элегантные системы "Приборных Панелей Джарвиса" + орбитальные капсулы на них
            function makeDashBand_HUD_Rings(radiSys, pXa, pYa, pZa, enableCapsules=false) {
                const SLevel = new THREE.Group(); SLevel.rotation.set(pXa, pYa, pZa);
                let rndLvls = 2 + Math.floor(Math.random() * 4); // число дисковых-шин связи в орбите
                
                for(let lv = 0; lv<rndLvls; lv++) {
                    let dLocal = new THREE.Group();
                    let rLvSize = radiSys + lv*(Math.random()*0.8+0.2); 
                    
                    let pieceDiv = 4 + Math.floor(Math.random()*16); 
                    for (let pc=0; pc<pieceDiv; pc++){
                        let pSliceLn = (Math.PI*2)/pieceDiv * (0.3+Math.random()*0.45); // Обрываем интерфейсные рамки на пустые пространства
                        let rgBthk = lv % 3 === 0 ? 0.015 : (0.05 + Math.random()*0.08); // Тощина
                        
                        // Цвет кольца-деления
                        let bMatCol = CLRS.HotGold; let rxr = Math.random();
                        if (rxr>0.9) bMatCol = CLRS.DiamondPt; else if (rxr>0.75) bMatCol = CLRS.BurnOrange;
                        else if (rxr>0.6 && rgBthk>0.05) bMatCol = CLRS.Cyantific;
                        
                        let M_RG = new THREE.Mesh(
                            new THREE.RingGeometry(rLvSize, rLvSize+rgBthk, 32, 1, pc * ((Math.PI*2)/pieceDiv), pSliceLn),
                            new THREE.MeshBasicMaterial({color:bMatCol, side:THREE.DoubleSide, ...OvrBld, opacity: 0.15 + (Math.random()*0.45)})
                        );
                        dLocal.add(M_RG);
                        holoRings.push(M_RG.material);
                    }
                    dLocal.userData = {rz: (Math.random()-0.5)*0.012};

                    // ---- Если это главный орбитальный экватор, повесим физические спутники-кристаллы ---- //
                    if (enableCapsules && Math.random()>0.4) {
                        let objGeomsType = new THREE.TetrahedronGeometry(0.2, 0); // Мелкие пирады информации. 
                        let dataModlCnt = 2 + Math.floor(Math.random()*4); 
                        for(let stL=0; stL < dataModlCnt; stL++){
                            let dMeshCap = new THREE.Mesh(objGeomsType, new THREE.MeshBasicMaterial({color: CLRS.Cyantific, ...OvrBld, opacity:0.85}));
                            let angleCaps = (Math.PI*2)/dataModlCnt * stL; 
                            dMeshCap.position.x = rLvSize * Math.cos(angleCaps); dMeshCap.position.y = rLvSize * Math.sin(angleCaps);
                            // Сами маленькие кусочки данных тоже будем кувыркать вокруг себя во время полета
                            dMeshCap.userData = { isHologramNode: true, spinX: Math.random()*0.02, spinY: Math.random()*0.02 }; 
                            dLocal.add(dMeshCap);
                            UPDATERS.push(dMeshCap);
                        }
                    }

                    UPDATERS.push(dLocal); SLevel.add(dLocal);
                }
                UNI_GRP.add(SLevel);
            }
            
            // Создаем многомерные разломанные панели - одна плоская/толстая орбита с Кубами/Кристаллами Информации
            makeDashBand_HUD_Rings(6.4, 0,0,0, true);
            makeDashBand_HUD_Rings(5.5, Math.PI/2,0,0);
            makeDashBand_HUD_Rings(7.1, 0, Math.PI/2.1, 0, true);
            makeDashBand_HUD_Rings(7.8, Math.PI/6, Math.PI/3.2, 0.4);


            // ----- КОМПОНЕНТ 5: ТОНКИЙ АСТРАЛЬНЫЙ ОКУТЫВАЮЩИЙ "ЗЕМНОЙ" ШАР -----
            // Сфера-сетка глобус поверх всей конструкции телеметрии. Идеальная проволочная структура без полигональной серости!
            let superSphereGeo = new THREE.WireframeGeometry(new THREE.SphereGeometry(6.6, 56, 30));
            let netGlob = new THREE.LineSegments(superSphereGeo, new THREE.LineBasicMaterial({color: CLRS.BurnOrange, ...OvrBld, opacity:0.07}));
            netGlob.userData = {rx: 0.0006, rz: 0.0002}; 
            UNI_GRP.add(netGlob); UPDATERS.push(netGlob);


            // Сохраняем ссылки на ключевые объекты — для подсветки активности ЛУЧА
            window.LUCH_HOLO = {
                coreDia, cageDodeca1, cageIcosa1, coreFire, netGlob,
                rings: holoRings, updaters: UPDATERS
            };
            applyAIState(AI_STATE);


            engineInst = true; 
        }

        // --- ДВИГАТЕЛЬ СЦЕНЫ, ПЕРЕМЕШИВАЮЩИЙ ГЕОМЕТРИЮ (Вращаем всё по заложенным userdata векторам)
        function jarvisLoopProc() {
            if (!showCore) return; 
            sysFrame = requestAnimationFrame(jarvisLoopProc);
            
            // Базовый покачивающий и вечный параллакс самого ядра Вселенной! 
            if(UNI_GRP) { 
                UNI_GRP.rotation.y += 0.00045; 
                UNI_GRP.rotation.z += 0.00018; 
            }
            
            for(let itms = 0; itms < UPDATERS.length; itms++) {
                let eMsh = UPDATERS[itms]; let udta = eMsh.userData;
                // Базовые облеты компонентов. (Если есть параметры вращения в user data)
                if(udta.rx !== undefined) eMsh.rotation.x += udta.rx;
                if(udta.ry !== undefined) eMsh.rotation.y += udta.ry;
                if(udta.rz !== undefined) eMsh.rotation.z += udta.rz;

                // Если это наши спутники-Данные. Кувыркаем их самих, пока их контейнер DLocal кружится вокруг всей базы!
                if(udta.isHologramNode) { eMsh.rotation.x += udta.spinX; eMsh.rotation.y += udta.spinY; }
            }

            if (CTROLS) CTROLS.update();
            if (RDR && SCE && CM) RDR.render(SCE, CM);
        }

        // --- 3. BACKGROUND NETWORK PINGS (Для Таймеров Сервера Консоли) --- 
        setInterval(async () => {
            try {
                const rqs = await fetch('/api/alerts'); if(!rqs.ok) return;
                const payl = await rqs.json();
                if (payl.alerts?.length > 0) {
                    payl.alerts.forEach(async (alItem) => {
                        let sysTbx = addMessage('💠 INCOMING DATALINK: ' + alItem.description, 'ai');
                        sysTbx.style.borderColor = "var(--neon-pink)"; sysTbx.style.boxShadow = "var(--shadow-glow-pink)";
                        try {
                            const bbb = await (await fetch('/api/alert_audio?t=' + Date.now())).blob();
                            let wpAud = new Audio(URL.createObjectURL(bbb));
                            wpAud.play().catch(()=>{
                                let bcBt = document.createElement('button'); bcBt.className = 'play-audio-btn';
                                bcBt.style.color = "var(--neon-pink)"; bcBt.style.borderColor="var(--neon-pink)";
                                bcBt.innerHTML = '🔊 ACTIVATE LINK SIGNAL'; bcBt.onclick = ()=>wpAud.play();
                                sysTbx.appendChild(document.createElement('br')); sysTbx.appendChild(bcBt);
                            });
                        } catch (er) {}
                    });
                }
            } catch(e) {}
        }, 2500); 


        // --- 4. ГЕОЛОКАЦИЯ / НАВИГАТОР (Leaflet + OpenStreetMap) ---
        const mapPanel = document.getElementById('mapPanel');
        const mapToggleBtn = document.getElementById('mapToggle');
        const mapStatus = document.getElementById('mapStatus');
        const navDestInput = document.getElementById('navDest');
        const navBuildBtn = document.getElementById('navBuildBtn');

        let map = null, userMarker = null, userCircle = null, routeLayer = null, destMarker = null;
        let geoWatchId = null, lastSentPos = null, destPos = null, userInteracted = false;

        function setMapStatus(text, ok) {
            mapStatus.textContent = text;
            mapStatus.dataset.ok = ok ? '1' : '0';
        }

        function initMap() {
            if (map) return;
            map = L.map('map').setView([55.75, 37.61], 13);
            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                attribution: '&copy; OpenStreetMap',
                maxZoom: 19
            }).addTo(map);
            map.on('click', onMapClick);
            // Если пользователь двигает/зумит карту сам — не притягиваем её обратно к маркеру
            map.on('dragstart', () => userInteracted = true);
            map.on('zoomstart', () => userInteracted = true);
        }

        function toggleMap() {
            const open = mapPanel.classList.toggle('open');
            mapToggleBtn.classList.toggle('active', open);
            if (open) {
                initMap();
                setTimeout(() => { if (map) map.invalidateSize(); }, 100);
                // При открытии один раз центрируем на текущей позиции
                if (userMarker && lastKnownPos && !userInteracted) {
                    map.setView([lastKnownPos.lat, lastKnownPos.lng], Math.max(map.getZoom(), 16));
                }
                startGeolocation();
            } else {
                stopGeolocation();
            }
        }

        let lastKnownPos = null;

        function startGeolocation() {
            if (!navigator.geolocation) { setMapStatus('Геолокация не поддерживается браузером', false); return; }
            setMapStatus('Запрос геолокации...', false);
            if (geoWatchId !== null) return;
            geoWatchId = navigator.geolocation.watchPosition(
                onGeoSuccess, onGeoError,
                { enableHighAccuracy: true, timeout: 15000, maximumAge: 5000 }
            );
        }

        function stopGeolocation() {
            if (geoWatchId !== null) { navigator.geolocation.clearWatch(geoWatchId); geoWatchId = null; }
        }

        function centerOnUser() {
            if (!map) return;
            if (lastKnownPos) { map.setView([lastKnownPos.lat, lastKnownPos.lng], Math.max(map.getZoom(), 16)); }
            userInteracted = false;   // вернуть автоматическое следование
        }

        function onGeoSuccess(pos) {
            const la = pos.coords.latitude, lo = pos.coords.longitude, acc = pos.coords.accuracy;
            setMapStatus(`GPS: ${la.toFixed(5)}, ${lo.toFixed(5)} ±${Math.round(acc)} м`, true);
            lastKnownPos = { lat: la, lng: lo, accuracy: acc, source: 'browser' };
            updateMarker(lastKnownPos);
            sendGeolocationToServer(la, lo, acc);
            addHistoryPoint({ lat: la, lng: lo });
            // Если ИИ запрашивал свежую позицию — погасили запрос после первой отправки
            if (locRequestPending) {
                locRequestPending = false;
                fetch('/api/location/request/resolve', { method: 'POST' }).catch(()=>{});
            }
        }

        // ИИ может запросить координаты клиента (команда request_location) —
        // проверяем флаг на сервере и при необходимости включаем геолокацию
        let locRequestPending = false;
        setInterval(async () => {
            try {
                const r = await fetch('/api/location/request');
                const d = await r.json();
                if (d && d.pending) {
                    locRequestPending = true;
                    lastSentPos = null;                    // снять «тюльпан» срочности
                    if (geoWatchId === null) startGeolocation();
                }
            } catch (e) { /* сервер недоступен */ }
        }, 3000);

        // Отправляем координаты на сервер (не чаще раза в 8 сек)
        function sendGeolocationToServer(lat, lng, accuracy) {
            const now = Date.now();
            if (lastSentPos && (now - lastSentPos) < 8000) return;
            lastSentPos = now;
            fetch('/api/location', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ lat, lng, accuracy, source: 'browser' })
            }).catch(()=>{});
        }

        function onGeoError(err) {
            setMapStatus('Геолокация недоступна: ' + err.message, false);
        }

        function onMapClick(e) {
            destPos = { lat: e.latlng.lat, lng: e.latlng.lng };
            e.target.openPopup();
        }

        function updateMarker(pos) {
            const firstFix = !userMarker;
            initMap();
            if (userMarker) { userMarker.setLatLng([pos.lat, pos.lng]); }
            else { userMarker = L.circleMarker([pos.lat, pos.lng], {
                radius: 8, color: '#2ecc71', weight: 2, fillColor: '#2ecc71', fillOpacity: 0.5 }).addTo(map);
                userMarker.bindPopup('Текущая позиция');
            }
            if (userCircle) userCircle.setLatLng([pos.lat, pos.lng]).setRadius(pos.accuracy || 10);
            else userCircle = L.circle([pos.lat, pos.lng], { radius: pos.accuracy || 10, color: '#2ecc71', opacity: 0.25 }).addTo(map);
            // Центрируем карту только при первом «фиксе» и если юзер сам карту не двигал
            if (firstFix && !userInteracted) {
                map.setView([pos.lat, pos.lng], Math.max(map.getZoom(), 16));
            }
        }

        // История перемещений (слой с лимитом на 100 точек)
        function addHistoryPoint(pos) {
            if (!map) return;
            if (!map.historyLayer) map.historyLayer = L.layerGroup().addTo(map);
            const m = L.circleMarker([pos.lat, pos.lng], { radius: 3, color: '#48c9b0', fillColor: '#48c9b0', fillOpacity: 0.5 });
            m.addTo(map.historyLayer);
            while (map.historyLayer.getLayers().length > 100) map.historyLayer.removeLayer(map.historyLayer.getLayers()[0]);
        }

        // Построение маршрута + голосовой режим навигатора (сервер: geocode + OSRM + steps)
        let navMode = false;

        const navStopBtn = document.getElementById('navStopBtn');
        const navManeuverBanner = document.getElementById('navManeuverBanner');
        const navManeuverText = document.getElementById('navManeuverText');
        const navManeuverDist = document.getElementById('navManeuverDist');

        function showManeuver(man) {
            if (!man) { navManeuverBanner.style.display = 'none'; return; }
            navManeuverText.textContent = man.text || 'Двигайтесь по маршруту';
            navManeuverDist.textContent = man.distance_m != null ? `${man.distance_m} м` : '';
            navManeuverBanner.style.display = 'flex';
            // Эффект обновления баннера
            navManeuverBanner.style.animation = 'none';
            void navManeuverBanner.offsetWidth;
            navManeuverBanner.style.animation = '';
        }

        function setNavModeUI(on) {
            navMode = on;
            navStopBtn.style.display = on ? '' : 'none';
            navBuildBtn.classList.toggle('active', on);
        }

        async function buildRoute() {
            const dest = navDestInput.value.trim();
            if (!dest) { setMapStatus('Укажи, куда едем (адрес или фраза)', false); return; }
            if (!map) initMap();
            try {
                const res = await fetch('/api/navigator/start', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ destination: dest })
                });
                const d = await res.json();
                const route = d && d.data;
                if (!route || route.status !== 'navigation_started') {
                    setMapStatus('Не удалось построить маршрут: ' + ((route && route.message) || 'неизвестная ошибка'), false);
                    return;
                }
                destPos = route.destination_coords;
                initMap();
                destMarker = destMarker || L.marker([destPos.lat, destPos.lng]).addTo(map);
                destMarker.setLatLng([destPos.lat, destPos.lng]).bindPopup(route.destination).openPopup();
                if (routeLayer) map.removeLayer(routeLayer);
                const coords = (route.geometry || []);
                if (coords.length) {
                    routeLayer = L.polyline(coords.filter(c => Array.isArray(c) && c.length >= 2),
                        { color: '#f1c40f', weight: 5, opacity: 0.7 }).addTo(map);
                    map.fitBounds(routeLayer.getBounds().pad(0.1));
                } else {
                    const f = route.from || { lat: 0, lng: 0 };
                    routeLayer = L.polyline([[f.lat, f.lng], [destPos.lat, destPos.lng]],
                        { color: '#f1c40f', weight: 3, dashArray: '6,4' }).addTo(map);
                    setMapStatus('OSRM недоступен — прямая линия до цели', false);
                }
                setMapStatus(`Маршрут: ${route.distance_km} км · ~${Math.round(route.duration_min)} мин`, true);
                showManeuver(route.next_maneuver);
                setNavModeUI(true);
                startGeolocation();
            } catch (e) {
                setMapStatus('Ошибка построения маршрута: ' + e.message, false);
            }
        }

        async function stopNavMode() {
            try {
                await fetch('/api/navigator/stop', { method: 'POST' });
            } catch (e) { /* сервер может быть недоступен */ }
            setNavModeUI(false);
            showManeuver(null);
            setMapStatus('Навигация остановлена', true);
        }

        // Опрос состояния навигатора: обновляем баннер манёвра и позицию
        setInterval(async () => {
            if (!navMode) return;
            try {
                const res = await fetch('/api/navigator/status');
                const d = await res.json();
                if (!d || !d.active) { setNavModeUI(false); showManeuver(null); return; }
                if (d.next_maneuver) showManeuver(d.next_maneuver);
                if (d.current_location && d.current_location.lat != null && lastKnownPos) {
                    const mlat = d.current_location.lat, mlng = d.current_location.lng;
                    const gps = lastKnownPos;
                    if (Math.abs(mlat - gps.lat) > 0.000001 || Math.abs(mlng - gps.lng) > 0.000001) {
                        updateMarker({ lat: mlat, lng: mlng, accuracy: gps.accuracy, source: 'server' });
                    }
                }
            } catch (e) { /* сервер недоступен */ }
        }, 2000);
        

        // --- 5. АКТИВНОСТЬ ЛУЧА НА 3D-ЯДРЕ (по состоянию с сервера) ---
        const holoStatusEl = document.getElementById('holoStatus');
        let AI_STATE = 'idle';

        // Каждое состояние: основной цвет ядра, цвет «огня», скорость, яркость, подпись, HTML-цвет для статуса
        const STATE_THEME = {
            idle:      { color: 0x00f3ff, fire: 0xff3800, speed: 1.0, intensity: 0.3, label: 'ПОКОЙ',      css: '#4df8ff' },
            listening: { color: 0xf5c2e7, fire: 0xffb700, speed: 1.2, intensity: 0.45, label: 'СЛУШАЕТ',    css: '#f5c2e7' },
            thinking:  { color: 0x7a5cff, fire: 0x00f3ff, speed: 2.4, intensity: 0.7,  label: 'ДУМАЕТ',     css: '#a78bfa' },
            speaking:  { color: 0xffb700, fire: 0xff3800, speed: 1.7, intensity: 0.55, label: 'ГОВОРИТ',    css: '#fab387' },
            command:   { color: 0x2ecc71, fire: 0xf1c40f, speed: 3.0, intensity: 0.95, label: 'ВЫПОЛНЯЕТ КОМАНДУ', css: '#a6e3a1' },
            error:     { color: 0xf38ba8, fire: 0xff3800, speed: 1.4, intensity: 0.7,  label: 'ОШИБКА',     css: '#f38ba8' },
        };

        function applyAIState(state) {
            AI_STATE = STATE_THEME[state] ? state : 'idle';
            const t = STATE_THEME[AI_STATE];
            if (holoStatusEl) {
                holoStatusEl.textContent = 'РЕЖИМ: ' + t.label;
                holoStatusEl.style.color = t.css;
                holoStatusEl.style.textShadow = `0 0 22px ${t.css}`;
            }
            const h = window.LUCH_HOLO;
            if (!h) return;

            if (h.coreDia) {
                h.coreDia.material.color.setHex(t.color);
                h.coreDia.material.opacity = 0.08 + 0.14 * t.intensity;
            }
            if (h.coreFire) {
                h.coreFire.material.color.setHex(t.fire);
                h.coreFire.material.opacity = 0.25 + 0.55 * t.intensity;
                h.coreFire.material.size = 0.03 + 0.035 * t.intensity;
            }
            // Оболочки-каркасы
            if (h.cageDodeca1) { h.cageDodeca1.material.color.setHex(t.color); h.cageDodeca1.material.opacity = 0.15 + 0.25 * t.intensity; }
            if (h.cageIcosa1)  { h.cageIcosa1.material.color.setHex(t.color); h.cageIcosa1.material.opacity = 0.10 + 0.18 * t.intensity; }
            if (h.netGlob)     { h.netGlob.material.color.setHex(t.color);     h.netGlob.material.opacity = 0.05 + 0.10 * t.intensity; }
            // Кольца-шкалы
            if (h.rings) h.rings.forEach(m => {
                m.color.setHex(t.color);
                m.opacity = (0.12 + 0.4 * t.intensity) * (0.5 + Math.random() * 0.5);
            });
            // Скорость вращения: сохраняем базу при первом применении и умножаем на speed
            h.updaters.forEach(u => {
                const ud = u.userData;
                if (!ud) return;
                if (ud.__base === undefined) {
                    ud.__base = { rx: ud.rx || 0, ry: ud.ry || 0, rz: ud.rz || 0 };
                }
                ud.rx = ud.__base.rx * t.speed;
                ud.ry = ud.__base.ry * t.speed;
                ud.rz = ud.__base.rz * t.speed;
            });
        }

        // Опрос состояния LУЧА с сервера (раз в секунду)
        setInterval(async () => {
            try {
                const r = await fetch('/api/state');
                const d = await r.json();
                if (d && d.state) applyAIState(d.state);
            } catch (e) { /* сервер может быть недоступен */ }
        }, 1000); 

