(() => {
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
    const finePointer = window.matchMedia("(hover: hover) and (pointer: fine)");

    if (reduceMotion.matches) {
        document.documentElement.classList.add("motion-reduced");
        return;
    }

    document.documentElement.classList.add("motion-enabled");

    const revealTargets = document.querySelectorAll([
        ".hero-copy > *",
        ".hero-visual",
        ".section-heading",
        ".filter-bar",
        ".adoption-filter-bar",
        ".fundraising-filter",
        ".map-toolbar",
        ".case-card",
        ".adoption-card",
        ".campaign-card",
        ".watercolor-action-heading",
        ".watercolor-action",
        ".knowledge-hub-feature",
        ".knowledge-topic-card",
        ".knowledge-safety-note",
        ".team-hero-copy > *",
        ".team-hero-photo",
        ".team-value-grid article",
        ".team-card",
        ".team-callout-inner",
        ".panel",
        ".empty-state",
        ".profile-quick-links a",
    ].join(","));

    revealTargets.forEach((element, index) => {
        element.classList.add("motion-reveal");
        element.style.setProperty("--reveal-delay", `${(index % 5) * 55}ms`);
    });

    if ("IntersectionObserver" in window) {
        const revealObserver = new IntersectionObserver((entries, observer) => {
            entries.forEach((entry) => {
                if (!entry.isIntersecting) return;
                entry.target.classList.add("is-visible");
                observer.unobserve(entry.target);
            });
        }, { rootMargin: "0px 0px -8%", threshold: 0.08 });

        revealTargets.forEach((element) => revealObserver.observe(element));
    } else {
        revealTargets.forEach((element) => element.classList.add("is-visible"));
    }

    if (finePointer.matches) {
        const tiltTargets = document.querySelectorAll([
            "[data-motion-tilt]",
            ".case-card",
            ".adoption-card",
            ".campaign-card",
            ".profile-quick-links a",
        ].join(","));

        tiltTargets.forEach((element) => {
            element.classList.add("motion-tilt");
            const strength = Number(element.dataset.tiltStrength || 4);

            element.addEventListener("pointermove", (event) => {
                const bounds = element.getBoundingClientRect();
                const x = (event.clientX - bounds.left) / bounds.width - 0.5;
                const y = (event.clientY - bounds.top) / bounds.height - 0.5;
                element.style.setProperty("--tilt-x", `${(-y * strength).toFixed(2)}deg`);
                element.style.setProperty("--tilt-y", `${(x * strength).toFixed(2)}deg`);
                element.style.setProperty("--shine-x", `${((x + 0.5) * 100).toFixed(1)}%`);
                element.style.setProperty("--shine-y", `${((y + 0.5) * 100).toFixed(1)}%`);
                element.classList.add("is-tilting");
            });

            element.addEventListener("pointerleave", () => {
                element.style.setProperty("--tilt-x", "0deg");
                element.style.setProperty("--tilt-y", "0deg");
                element.classList.remove("is-tilting");
            });
        });
    }

    const hero = document.querySelector(".hero-panel");
    const parallaxLayer = document.querySelector("[data-parallax-layer]");
    if (hero && parallaxLayer) {
        let ticking = false;

        const updateParallax = () => {
            const bounds = hero.getBoundingClientRect();
            const progress = Math.max(0, Math.min(1, -bounds.top / Math.max(bounds.height, 1)));
            hero.style.setProperty("--hero-scroll", `${(progress * 28).toFixed(1)}px`);
            parallaxLayer.style.setProperty("--depth-scroll", `${(progress * -18).toFixed(1)}px`);
            ticking = false;
        };

        window.addEventListener("scroll", () => {
            if (ticking) return;
            ticking = true;
            window.requestAnimationFrame(updateParallax);
        }, { passive: true });

        updateParallax();
    }

    const watercolorScene = document.querySelector("[data-watercolor-scene]");
    if (watercolorScene && finePointer.matches) {
        watercolorScene.addEventListener("pointermove", (event) => {
            const bounds = watercolorScene.getBoundingClientRect();
            const x = (event.clientX - bounds.left) / bounds.width - 0.5;
            const y = (event.clientY - bounds.top) / bounds.height - 0.5;
            watercolorScene.style.setProperty(
                "--watercolor-shift-x",
                `${(x * 7).toFixed(1)}px`,
            );
            watercolorScene.style.setProperty(
                "--watercolor-shift-y",
                `${(y * 5).toFixed(1)}px`,
            );
        });

        watercolorScene.addEventListener("pointerleave", () => {
            watercolorScene.style.setProperty("--watercolor-shift-x", "0px");
            watercolorScene.style.setProperty("--watercolor-shift-y", "0px");
        });
    }
})();
