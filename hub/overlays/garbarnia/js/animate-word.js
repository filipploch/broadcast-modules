function animateWord(
    elementId,
    word,
    duration,
    elementToHideId,
    class1,
    class2,
    teamName14,
    cellSize,
    svgCurves
) {
    const container = document.getElementById(elementId);
    if (!container) return;

    word = word || "GOOOOL";

    const defaultSvgCurves = {
        G: {
            viewBox: "0 0 100 100",
            paths: [
                "M52 10C30 10 14 27 14 50C14 73 31 90 54 90C68 90 80 84 87 74V50H55V63H73V67C69 73 62 76 54 76C39 76 29 65 29 50C29 35 39 24 53 24C62 24 69 28 74 36L86 28C79 17 67 10 52 10Z"
            ]
        },
        O: {
            viewBox: "0 0 100 100",
            paths: [
                "M50 10C27 10 11 27 11 50C11 73 27 90 50 90C73 90 89 73 89 50C89 27 73 10 50 10ZM50 25C64 25 74 35 74 50C74 65 64 75 50 75C36 75 26 65 26 50C26 35 36 25 50 25Z"
            ],
            fillRule: "evenodd"
        },
        L: {
            viewBox: "0 0 100 100",
            paths: [
                "M22 12H38V75H80V88H22V12Z"
            ]
        }
    };

    svgCurves = svgCurves || defaultSvgCurves;

    const elementToHide = elementToHideId ? document.getElementById(elementToHideId) : null;
    if (elementToHide) elementToHide.style.visibility = "hidden";

    container.innerHTML = "";

    const teamFont = cellSize * 0.55;
    const wordContainerWidth = word.length * cellSize;

    // Container jest maską: przyjmuje finalne wymiary wordContainer.
    container.style.width = wordContainerWidth + "px";
    container.style.height = cellSize + "px";
    container.style.overflow = "hidden";
    container.style.position = "relative";

    const wordContainer = document.createElement("div");
    wordContainer.style.display = "inline-flex";
    wordContainer.style.position = "absolute";
    wordContainer.style.left = "0";
    wordContainer.style.top = "0";
    wordContainer.style.opacity = "1";
    wordContainer.style.height = cellSize + "px";
    wordContainer.style.width = wordContainerWidth + "px";
    wordContainer.style.willChange = "transform,background";
    wordContainer.style.transformOrigin = "50% 50%";

    // Start: wordContainer znajduje się poniżej widocznego obszaru container.
    wordContainer.style.transform = `translate(0px, ${cellSize}px) scale(1)`;

    container.appendChild(wordContainer);

    const svgItems = [];

    for (let char of word) {
        const box = document.createElement("div");
        box.style.width = cellSize + "px";
        box.style.height = cellSize + "px";
        box.style.display = "flex";
        box.style.alignItems = "center";
        box.style.justifyContent = "center";

        if (typeof addClassName === "function") {
            addClassName(box, "charBox");
        } else {
            box.classList.add("charBox");
        }

        const svg = createSvgForChar(char, svgCurves);
        svg.style.display = "block";
        svg.style.width = (cellSize * 0.68) + "px";
        svg.style.height = (cellSize * 0.68) + "px";
        svg.style.transform = "scale(1)";
        svg.style.transformOrigin = "50% 50%";
        svg.style.willChange = "transform,color,fill";

        box.appendChild(svg);
        wordContainer.appendChild(box);
        svgItems.push(svg);
    }

    function createSvgForChar(char, curves) {
        const NS = "http://www.w3.org/2000/svg";
        const key = String(char).toUpperCase();
        const def = curves[key];

        const svg = document.createElementNS(NS, "svg");
        svg.setAttribute("xmlns", NS);
        svg.setAttribute("viewBox", def && def.viewBox ? def.viewBox : "0 0 100 100");
        svg.setAttribute("aria-label", key);
        svg.setAttribute("role", "img");
        svg.setAttribute("preserveAspectRatio", "xMidYMid meet");

        if (!def) {
            const text = document.createElementNS(NS, "text");
            text.textContent = key;
            text.setAttribute("x", "50");
            text.setAttribute("y", "68");
            text.setAttribute("text-anchor", "middle");
            text.setAttribute("font-size", "64");
            text.setAttribute("font-family", "sans-serif");
            text.setAttribute("font-weight", "700");
            text.setAttribute("fill", "currentColor");
            svg.appendChild(text);
            return svg;
        }

        const paths = Array.isArray(def.paths) ? def.paths : [def.path || def.d];

        paths.filter(Boolean).forEach(d => {
            const path = document.createElementNS(NS, "path");
            path.setAttribute("d", d);
            path.setAttribute("fill", "currentColor");
            if (def.fillRule) path.setAttribute("fill-rule", def.fillRule);
            if (def.clipRule) path.setAttribute("clip-rule", def.clipRule);
            svg.appendChild(path);
        });

        return svg;
    }

    const easeOutBack = t => 1 + (--t) * t * (2.7 * t + 1.7);

    function easeInOutCubic(t) {
        return t < 0.5
            ? 4 * t * t * t
            : 1 - Math.pow(-2 * t + 2, 3) / 2;
    }

    function clamp255(v) {
        return Math.max(0, Math.min(255, Math.round(v)));
    }

    function rgbToHex(r, g, b) {
        return "#" + [r, g, b].map(v => {
            const h = clamp255(v).toString(16);
            return h.length === 1 ? "0" + h : h;
        }).join("");
    }

    function parseCssColor(value, fallback) {
        if (!value || value === "transparent") return fallback;
        const nums = value.match(/[\d.]+/g);
        if (!nums || nums.length < 3) return fallback;

        return [
            clamp255(Number(nums[0])),
            clamp255(Number(nums[1])),
            clamp255(Number(nums[2]))
        ];
    }

    function darken(rgb, percent) {
        return rgb.map(v => Math.max(0, Math.floor(v * (1 - percent))));
    }

    function gradientFrom(rgb) {
        const dark = darken(rgb, 0.1);
        return `linear-gradient(to bottom,
            rgb(${rgb[0]},${rgb[1]},${rgb[2]}),
            rgb(${dark[0]},${dark[1]},${dark[2]}))`;
    }

    function getClassVisuals(cls) {
        const tmp = document.createElement("div");
        tmp.className = cls;
        tmp.style.position = "absolute";
        tmp.style.left = "-9999px";
        tmp.style.top = "-9999px";
        tmp.style.width = "1px";
        tmp.style.height = "1px";
        tmp.style.pointerEvents = "none";

        document.body.appendChild(tmp);

        const styles = getComputedStyle(tmp);
        const visuals = {
            background: parseCssColor(styles.backgroundColor, [0, 0, 0]),
            fill: parseCssColor(styles.color, [255, 255, 255])
        };

        document.body.removeChild(tmp);
        return visuals;
    }

    const style1 = getClassVisuals(class1);
    const style2 = getClassVisuals(class2);

    const bg1 = style1.background;
    const bg2 = style2.background;
    const fill1 = style1.fill;
    const fill2 = style2.fill;

    function setSvgColor(rgb) {
        const color = rgbToHex(rgb[0], rgb[1], rgb[2]);
        svgItems.forEach(svg => {
            svg.style.color = color;
        });
    }

    function animateGradient(from, to, time, cb) {
        if (time <= 0) {
            wordContainer.style.background = gradientFrom(to);
            if (cb) cb();
            return;
        }

        const start = performance.now();

        function frame(now) {
            let t = (now - start) / time;
            if (t > 1) t = 1;

            const rgb = [
                Math.round(from[0] + (to[0] - from[0]) * t),
                Math.round(from[1] + (to[1] - from[1]) * t),
                Math.round(from[2] + (to[2] - from[2]) * t)
            ];

            wordContainer.style.background = gradientFrom(rgb);

            if (t < 1) requestAnimationFrame(frame);
            else if (cb) cb();
        }

        requestAnimationFrame(frame);
    }

    function animateSvgColor(from, to, time, cb) {
        if (time <= 0) {
            setSvgColor(to);
            if (cb) cb();
            return;
        }

        const start = performance.now();

        function frame(now) {
            let t = (now - start) / time;
            if (t > 1) t = 1;

            const rgb = [
                Math.round(from[0] + (to[0] - from[0]) * t),
                Math.round(from[1] + (to[1] - from[1]) * t),
                Math.round(from[2] + (to[2] - from[2]) * t)
            ];

            setSvgColor(rgb);

            if (t < 1) requestAnimationFrame(frame);
            else if (cb) cb();
        }

        requestAnimationFrame(frame);
    }

    function animateScale(el, from, to, time, cb) {
        if (time <= 0) {
            el.style.transform = `scale(${to})`;
            if (cb) cb();
            return;
        }

        const start = performance.now();

        function frame(now) {
            let t = (now - start) / time;
            if (t > 1) t = 1;

            const eased = easeOutBack(t);
            const val = from + (to - from) * eased;
            el.style.transform = `scale(${val})`;

            if (t < 1) requestAnimationFrame(frame);
            else if (cb) cb();
        }

        requestAnimationFrame(frame);
    }

    function animateTransformKeyframes(el, keyframes, time, cb) {
        if (time <= 0) {
            const last = keyframes[keyframes.length - 1];
            el.style.transform = `translate(${last.x}px, ${last.y}px) scale(${last.scale})`;
            if (cb) cb();
            return;
        }

        const startTime = performance.now();

        function frame(now) {
            let t = (now - startTime) / time;
            if (t > 1) t = 1;

            let a = keyframes[0];
            let b = keyframes[keyframes.length - 1];

            for (let i = 0; i < keyframes.length - 1; i++) {
                if (t >= keyframes[i].p && t <= keyframes[i + 1].p) {
                    a = keyframes[i];
                    b = keyframes[i + 1];
                    break;
                }
            }

            const localT = (t - a.p) / (b.p - a.p);
            const eased = easeInOutCubic(localT);

            const x = a.x + (b.x - a.x) * eased;
            const y = a.y + (b.y - a.y) * eased;
            const scale = a.scale + (b.scale - a.scale) * eased;

            el.style.transform = `translate(${x}px, ${y}px) scale(${scale})`;

            if (t < 1) {
                requestAnimationFrame(frame);
            } else {
                const last = keyframes[keyframes.length - 1];
                el.style.transform = `translate(${last.x}px, ${last.y}px) scale(${last.scale})`;
                if (cb) cb();
            }
        }

        requestAnimationFrame(frame);
    }

    function animateWordContainerIntro(cb) {
        const introDuration = duration * 2;

        const start = {
            x: cellSize * 6,
            y: cellSize,
            scale: 1
        };

        const peak = {
            x: cellSize * 5,
            y: -cellSize * 0.22,
            scale: 3
        };

        const end = {
            x: 0,
            y: 0,
            scale: 1
        };

        animateTransformKeyframes(
            wordContainer,
            [
                { p: 0, ...start },
                { p: 0.58, ...peak },
                { p: 1, ...end }
            ],
            introDuration,
            cb
        );
    }

    // ---------- SEQUENCE ----------

    wordContainer.style.background = gradientFrom(bg1);
    setSvgColor(fill1);

    // Animacja wejścia rusza zawsze od razu.
    animateWordContainerIntro();

    // Warianty plików różnią się tylko tą wartością:
    // 0 = animacja liter rusza jednocześnie z animacją wejścia.
    // duration * 0.15 = lekkie opóźnienie animacji liter.
    const LETTER_ANIMATION_DELAY = 0;

    setTimeout(() => {
        startMainAnimation();
    }, LETTER_ANIMATION_DELAY);

    function startMainAnimation() {
        animateGradient(bg1, [255, 255, 255], duration);
        animateSvgColor(fill1, [255, 255, 255], duration);
        svgItems.forEach(svg => animateScale(svg, 1, 1.5, duration));

        setTimeout(() => {
            animateGradient([255, 255, 255], bg1, duration);
            animateSvgColor([255, 255, 255], fill1, duration);
            svgItems.forEach(svg => animateScale(svg, 1.5, 1, duration));
        }, duration);

        setTimeout(() => {
            startSymbolWave();
        }, duration * 2);
    }

    function startSymbolWave() {
        let i = 0;

        function next() {
            if (i >= svgItems.length) {
                swapClasses();
                return;
            }

            animateScale(svgItems[i], 1, 1.5, duration, () => {
                animateScale(svgItems[i], 1.5, 1, duration);
            });

            i++;
            setTimeout(next, duration);
        }

        next();
    }

    function swapClasses() {
        let count = 0;
        let state = false;

        function step() {
            if (count >= 4) {
                showTeam();
                return;
            }

            state = !state;

            animateGradient(
                state ? bg1 : bg2,
                state ? bg2 : bg1,
                0
            );

            animateSvgColor(
                state ? fill1 : fill2,
                state ? fill2 : fill1,
                0
            );

            count++;
            setTimeout(step, duration);
        }

        step();
    }

    function showTeam() {
        wordContainer.innerHTML = "";
        wordContainer.style.transform = "translate(0px, 0px) scale(1)";

        const team = document.createElement("div");

        team.textContent = (teamName14 || "").toUpperCase().slice(0, 14);
        team.style.fontSize = teamFont + "px";
        team.style.display = "flex";
        team.style.alignItems = "center";
        team.style.justifyContent = "center";
        team.style.height = cellSize + "px";
        team.style.width = "100%";
        team.style.color = rgbToHex(fill1[0], fill1[1], fill1[2]);

        wordContainer.appendChild(team);

        animateRandomBackground();
    }

    function animateRandomBackground() {
        let count = 0;

        function step() {
            const base = bg1;
            const rand = base.map(v => clamp255(v + (Math.random() * 0.6 - 0.3) * 255));

            animateGradient(base, rand, duration);

            count++;

            if (count < 4) setTimeout(step, duration);
            else finish();
        }

        step();
    }

    function finish() {
        wordContainer.style.opacity = "0";

        setTimeout(() => {
            container.innerHTML = "";
            if (elementToHide) elementToHide.style.visibility = "";
        }, duration);
    }
}
