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

    // ─────────────────────────────────────────────────────────────────────────
    // Bold, monospaced SVG paths — viewBox "0 0 100 100".
    // Stroke width equivalent: ~13–15 units (geometrically baked into fills).
    // Each glyph is horizontally centred inside the 100×100 cell.
    // Polish diacritics hang below the baseline (y > 80) as a small wedge/hook.
    // ─────────────────────────────────────────────────────────────────────────
    const defaultSvgCurves = {

        // ── Standard Latin ────────────────────────────────────────────────────

        A: {
            viewBox: "0 0 100 100",
            paths: [
                // Two legs + crossbar
                "M50 8L14 88H28L36 68H64L72 88H86L50 8Z M42 55L50 33L58 55H42Z"
            ],
            fillRule: "evenodd"
        },
        B: {
            viewBox: "0 0 100 100",
            paths: [
                "M20 10H56C68 10 78 19 78 31C78 38 74 44 68 48C76 52 82 60 82 70C82 82 72 90 59 90H20V10Z M35 24V44H54C60 44 65 40 65 34C65 28 60 24 54 24H35Z M35 58V76H57C64 76 69 71 69 67C69 63 64 58 57 58H35Z"
            ],
            fillRule: "evenodd"
        },
        C: {
            viewBox: "0 0 100 100",
            paths: [
                "M52 18C32 18 15 34 15 54C15 74 32 90 52 90C65 90 77 83 84 72L72 64C68 71 61 75 52 75C40 75 30 65 30 54C30 43 40 33 52 33C61 33 68 37 72 44L84 36C77 25 65 18 52 18Z"
            ]
        },
        D: {
            viewBox: "0 0 100 100",
            paths: [
                "M20 10H50C70 10 84 28 84 50C84 72 70 90 50 90H20V10Z M35 24V76H49C61 76 69 64 69 50C69 36 61 24 49 24H35Z"
            ],
            fillRule: "evenodd"
        },
        E: {
            viewBox: "0 0 100 100",
            paths: [
                "M20 10H82V24H35V43H78V57H35V76H82V90H20V10Z"
            ]
        },
        F: {
            viewBox: "0 0 100 100",
            paths: [
                "M20 10H82V24H35V43H76V57H35V90H20V10Z"
            ]
        },
        G: {
            viewBox: "0 0 100 100",
            paths: [
                "M52 10C30 10 14 27 14 50C14 73 31 90 54 90C68 90 80 84 87 74V50H55V63H73V67C69 73 62 76 54 76C39 76 29 65 29 50C29 35 39 24 53 24C62 24 69 28 74 36L86 28C79 17 67 10 52 10Z"
            ]
        },
        H: {
            viewBox: "0 0 100 100",
            paths: [
                "M18 10H33V43H67V10H82V90H67V57H33V90H18V10Z"
            ]
        },
        I: {
            viewBox: "0 0 100 100",
            paths: [
                "M32 10H68V24H57V76H68V90H32V76H43V24H32V10Z"
            ]
        },
        J: {
            viewBox: "0 0 100 100",
            paths: [
                "M38 10H74V24H63V66C63 77 56 90 42 90C30 90 20 81 18 70L32 66C33 71 37 76 42 76C48 76 49 71 49 66V24H38V10Z"
            ]
        },
        K: {
            viewBox: "0 0 100 100",
            paths: [
                "M20 10H35V44L63 10H81L52 47L82 90H64L43 59L35 68V90H20V10Z"
            ]
        },
        L: {
            viewBox: "0 0 100 100",
            paths: [
                "M22 10H37V76H80V90H22V10Z"
            ]
        },
        M: {
            viewBox: "0 0 100 100",
            paths: [
                "M14 10H29L50 45L71 10H86V90H71V36L50 71L29 36V90H14V10Z"
            ]
        },
        N: {
            viewBox: "0 0 100 100",
            paths: [
                "M16 10H31L68 62V10H83V90H68L31 38V90H16V10Z"
            ]
        },
        O: {
            viewBox: "0 0 100 100",
            paths: [
                "M50 10C27 10 11 27 11 50C11 73 27 90 50 90C73 90 89 73 89 50C89 27 73 10 50 10ZM50 25C64 25 74 35 74 50C74 65 64 75 50 75C36 75 26 65 26 50C26 35 36 25 50 25Z"
            ],
            fillRule: "evenodd"
        },
        P: {
            viewBox: "0 0 100 100",
            paths: [
                "M20 10H58C72 10 82 21 82 36C82 51 72 62 58 62H35V90H20V10Z M35 24V48H56C63 48 67 43 67 36C67 29 63 24 56 24H35Z"
            ],
            fillRule: "evenodd"
        },
        Q: {
            viewBox: "0 0 100 100",
            paths: [
                "M50 10C27 10 11 27 11 50C11 65 19 78 31 85L24 96H38L43 88C45 89 47 90 50 90C73 90 89 73 89 50C89 27 73 10 50 10ZM50 25C64 25 74 35 74 50C74 58 70 65 65 70L58 60H44L54 75C52 75 51 75 50 75C36 75 26 65 26 50C26 35 36 25 50 25Z"
            ],
            fillRule: "evenodd"
        },
        R: {
            viewBox: "0 0 100 100",
            paths: [
                "M20 10H57C71 10 82 21 82 36C82 47 76 55 67 59L84 90H67L52 62H35V90H20V10Z M35 24V48H55C62 48 67 43 67 36C67 29 62 24 55 24H35Z"
            ],
            fillRule: "evenodd"
        },
        S: {
            viewBox: "0 0 100 100",
            paths: [
                "M50 10C33 10 19 21 19 36C19 51 31 56 46 60C57 63 65 65 65 71C65 74 62 77 54 77C45 77 38 72 34 65L21 73C27 83 39 90 54 90C72 90 80 80 80 70C80 55 68 50 53 46C43 43 34 41 34 35C34 32 37 24 50 24C58 24 64 28 67 35L80 27C75 17 63 10 50 10Z"
            ]
        },
        T: {
            viewBox: "0 0 100 100",
            paths: [
                "M14 10H86V24H57V90H43V24H14V10Z"
            ]
        },
        U: {
            viewBox: "0 0 100 100",
            paths: [
                "M18 10H33V60C33 68 41 76 50 76C59 76 67 68 67 60V10H82V60C82 76 67 90 50 90C33 90 18 76 18 60V10Z"
            ]
        },
        W: {
            viewBox: "0 0 100 100",
            paths: [
                "M8 10H23L35 62L48 10H52L65 62L77 10H92L72 90H58L50 55L42 90H28L8 10Z"
            ]
        },
        X: {
            viewBox: "0 0 100 100",
            paths: [
                "M16 10H33L50 38L67 10H84L60 50L84 90H67L50 62L33 90H16L40 50L16 10Z"
            ]
        },
        Y: {
            viewBox: "0 0 100 100",
            paths: [
                "M14 10H30L50 44L70 10H86L57 58V90H43V58L14 10Z"
            ]
        },
        Z: {
            viewBox: "0 0 100 100",
            paths: [
                "M16 10H84V24L36 76H84V90H16V76L64 24H16V10Z"
            ]
        },

        // ── Polish diacritics ─────────────────────────────────────────────────
        // Each diacritic is appended as a subpath below the base letter.
        // Ogonek (Ą, Ę): small right-hooking tail from bottom-right of stem.
        // Acute (Ć, Ó, Ś, Ź): short diagonal tick above letter, baked into paths below.
        // Overdot (Ż): filled circle above the bar.
        // Stroke (Ł): horizontal bar through the vertical stem.
        // ─────────────────────────────────────────────────────────────────────

        // Ą — A + ogonek
        "\u0104": {
            viewBox: "0 0 100 110",
            paths: [
                // A
                "M50 8L14 88H28L36 68H64L72 88H86L50 8Z M42 55L50 33L58 55H42Z",
                // ogonek — hook from bottom-right of right leg
                "M68 88C72 88 76 90 76 95C76 101 70 106 62 106C56 106 51 103 51 103L55 97C55 97 58 100 62 100C65 100 68 98 68 95C68 93 66 92 64 92H60V88H68Z"
            ],
            fillRule: "evenodd"
        },

        // Ć — C + acute
        "\u0106": {
            viewBox: "0 0 100 100",
            paths: [
                // acute above
                "M54 2L44 16H54L60 2H54Z",
                // C
                "M52 18C32 18 15 34 15 54C15 74 32 90 52 90C65 90 77 83 84 72L72 64C68 71 61 75 52 75C40 75 30 65 30 54C30 43 40 33 52 33C61 33 68 37 72 44L84 36C77 25 65 18 52 18Z"
            ]
        },

        // Ę — E + ogonek
        "\u0118": {
            viewBox: "0 0 100 110",
            paths: [
                // E
                "M20 10H82V24H35V43H78V57H35V76H82V90H20V10Z",
                // ogonek from bottom-right of baseline
                "M76 90C80 90 84 92 84 97C84 103 78 108 70 108C64 108 59 105 59 105L63 99C63 99 66 102 70 102C73 102 76 100 76 97C76 95 74 94 72 94H68V90H76Z"
            ]
        },

        // Ł — L + horizontal stroke through stem
        "\u0141": {
            viewBox: "0 0 100 100",
            paths: [
                // L with stroke
                "M22 10H37V42L52 50L37 58V90H22V58L12 50L22 42V10Z M37 76H80V90H37V76Z"
            ]
        },

        // Ó — O + acute
        "\u00D3": {
            viewBox: "0 0 100 100",
            paths: [
                // acute
                "M54 2L44 14H54L60 2H54Z",
                // O (shifted down 6 units)
                "M50 16C27 16 11 33 11 56C11 76 27 92 50 92C73 92 89 76 89 56C89 33 73 16 50 16ZM50 31C64 31 74 41 74 56C74 71 64 80 50 80C36 80 26 71 26 56C26 41 36 31 50 31Z"
            ],
            fillRule: "evenodd"
        },

        // Ś — S + acute
        "\u015A": {
            viewBox: "0 0 100 100",
            paths: [
                // acute
                "M54 2L44 14H54L60 2H54Z",
                // S (shifted slightly)
                "M50 15C33 15 19 26 19 41C19 56 31 61 46 65C57 68 65 70 65 76C65 79 62 82 54 82C45 82 38 77 34 70L21 78C27 88 39 94 54 94C72 94 80 85 80 75C80 60 68 55 53 51C43 48 34 46 34 40C34 37 37 29 50 29C58 29 64 33 67 40L80 32C75 22 63 15 50 15Z"
            ]
        },

        // Ź — Z + acute
        "\u0179": {
            viewBox: "0 0 100 100",
            paths: [
                // acute
                "M56 2L46 14H56L62 2H56Z",
                // Z (shifted slightly)
                "M16 14H84V28L36 80H84V94H16V80L64 28H16V14Z"
            ]
        },

        // Ż — Z + overdot
        "\u017B": {
            viewBox: "0 0 100 100",
            paths: [
                // overdot
                "M50 4C46 4 43 7 43 11C43 15 46 18 50 18C54 18 57 15 57 11C57 7 54 4 50 4Z",
                // Z
                "M16 22H84V36L36 80H84V94H16V80L64 36H16V22Z"
            ]
        },

        // Ź duplicate entry via literal character (belt & suspenders)
        // Handled above via unicode escape; alias below ensures both code paths work.

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
