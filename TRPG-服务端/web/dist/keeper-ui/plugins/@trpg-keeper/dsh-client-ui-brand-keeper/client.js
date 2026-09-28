window.__ModuleLoader__.load({
	id: "@trpg-keeper/dsh-client-ui-brand-keeper",
	factory: (require) => {
		var module = { exports: {} };
		var exports = module.exports;
		Object.defineProperty(exports, Symbol.toStringTag, { value: "Module" });
		let react_jsx_runtime = require("react/jsx-runtime");
		//#region lib/types/client/KeeperBrand.js
		// Keeper mark: d20 die silhouette (original geometry, no fish path reuse).
		// viewBox 24x24; icosahedron-ish hexagon + inner "20" facets.
		const KEEPER_MARK_VIEWBOX = { width: 24, height: 24 };
		function KeeperMark({ size, className }) {
			const s = size ?? 24;
			return (0, react_jsx_runtime.jsx)("svg", {
				width: s,
				height: s,
				viewBox: "0 0 24 24",
				className,
				"aria-hidden": true,
				children: (0, react_jsx_runtime.jsx)("path", {
					fill: "currentColor",
					d: "M12 1.8 21 7v10l-9 5.2L3 17V7l9-5.2Zm0 2.3L4.9 8.2v7.6L12 19.9l7.1-4.1V8.2L12 4.1Zm-1.1 4.6h2.2l1.7 4.3-2.8 2.7-2.8-2.7 1.7-4.3Z",
				}),
			});
		}
		// Keeper wordmark: pure text SVG (no third-party artwork reuse).
		// includeMark=false renders text only (mark comes from its own slot).
		function KeeperWordmark({ size, className, includeMark }) {
			const h = size ?? 24;
			const w = includeMark === false ? 120 : 144;
			return (0, react_jsx_runtime.jsx)("svg", {
				width: (w * h) / 24,
				height: h,
				viewBox: `0 0 ${w} 24`,
				className,
				"aria-hidden": true,
				role: "img",
				"aria-label": "TRPG Keeper",
				children: (0, react_jsx_runtime.jsxs)("text", {
					x: includeMark === false ? 4 : 28,
					y: 17,
					fill: "currentColor",
					fontSize: 14,
					fontFamily: "system-ui, sans-serif",
					children: "TRPG Keeper",
				}),
			});
		}
		//#endregion
		//#region lib/types/client/index.js
		/** Required service: the UI slot registry. */
		const inject = ["slots"];
		/**
		* Fill sidebar + hero brand slots as one declaration-aware registration set.
		* Non-official profile only (trpg-keeper); official occupant stays out.
		* @param ctx - Client root context.
		*/
		function apply(ctx) {
			ctx.slots.inject("sidebar.brand.mark", () => ctx.slots.inject("sidebar.brand.name", () => ctx.slots.inject("conversation.hero.brand.mark", function* () {
				yield ctx.slots.register({ name: "sidebar.brand.mark" }, KeeperMark);
				yield ctx.slots.register({ name: "sidebar.brand.name" }, KeeperWordmark);
				yield ctx.slots.register({ name: "conversation.hero.brand.mark" }, KeeperMark);
			})));
		}
		//#endregion
		exports.apply = apply;
		exports.inject = inject;
		exports.KeeperMark = KeeperMark;
		exports.KeeperWordmark = KeeperWordmark;
		exports.KEEPER_MARK_VIEWBOX = KEEPER_MARK_VIEWBOX;
		return module.exports;
	}
});
