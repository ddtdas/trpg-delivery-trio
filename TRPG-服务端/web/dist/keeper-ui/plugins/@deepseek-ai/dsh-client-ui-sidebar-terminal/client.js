window.__ModuleLoader__.load({
	id: "@deepseek-ai/dsh-client-ui-sidebar-terminal",
	factory: (require) => {
		var module = { exports: {} };
		var exports = module.exports;
		Object.defineProperty(exports, Symbol.toStringTag, { value: "Module" });
		let react_jsx_runtime = require("react/jsx-runtime");
		let react = require("react");
		let _deepseek_ai_dsh_client_ui_primitives = require("@deepseek-ai/dsh-client-ui-primitives");
		//#region lib/types/client/TerminalIcon.js
		/**
		* Render the tab title's terminal prompt in the surrounding text color.
		* @returns a decorative sixteen-pixel line glyph.
		*/
		function TerminalIcon() {
			return (0, react_jsx_runtime.jsxs)("svg", {
				width: "16",
				height: "16",
				viewBox: "0 0 16 16",
				fill: "none",
				"aria-hidden": "true",
				children: [(0, react_jsx_runtime.jsx)("path", {
					d: "M3 4L7 8L3 12",
					stroke: "currentColor"
				}), (0, react_jsx_runtime.jsx)("path", {
					d: "M9 12H13",
					stroke: "currentColor"
				})]
			});
		}
		/**
		* Render the guide's terminal card within the folder glyph's painted bounds.
		* @param props - canvas size and layout class supplied by the guide.
		* @returns a dark rounded terminal card with a white prompt.
		*/
		function TerminalGuideIcon({ size = 26, className }) {
			return (0, react_jsx_runtime.jsxs)("svg", {
				width: size,
				height: size,
				className,
				viewBox: "0 0 28 28",
				fill: "none",
				"aria-hidden": "true",
				children: [(0, react_jsx_runtime.jsx)("path", {
					d: "M22 5H6C4.34315 5 3 6.34315 3 8V21C3 22.6569 4.34315 24 6 24H22C23.6569 24 25 22.6569 25 21V8C25 6.34315 23.6569 5 22 5Z",
					fill: "#17191D"
				}), (0, react_jsx_runtime.jsx)("path", {
					d: "M8 10L12 14L8 18M15 18H17.5H20",
					stroke: "white",
					strokeWidth: "1.7",
					strokeLinejoin: "round"
				})]
			});
		}
		//#endregion
		//#region \0dsh-css:/home/runner/work/deepseek-harness/deepseek-harness/packages/client/ui-sidebar-terminal/src/client/TerminalGuide.module.css.mjs
		const css$1 = ".zjup-W_entry{box-sizing:border-box;border:.5px solid var(--dsw-alias-border-l3);background:var(--dsw-alias-bg-layer-1);border-radius:24px;align-items:stretch;width:100%;display:flex;overflow:hidden}.zjup-W_main{text-align:left;border-radius:24px 0 0 24px;flex:1;justify-content:flex-start;gap:14px;min-width:0;height:auto;min-height:56px;padding:14px 20px}.zjup-W_icon{flex:none}.zjup-W_text{flex-direction:column;gap:3px;min-width:0;display:flex}.zjup-W_title{color:var(--dsw-alias-label-primary);white-space:nowrap;text-overflow:ellipsis;font-size:14px;line-height:1.4;overflow:hidden}.zjup-W_description{color:var(--dsw-alias-label-caption);white-space:nowrap;text-overflow:ellipsis;font-size:13px;line-height:1.4;overflow:hidden}.zjup-W_trigger{border-radius:0 24px 24px 0;flex:none;align-self:stretch;width:44px;height:auto;padding:0}.zjup-W_trigger svg{width:18px;height:18px;color:var(--dsw-alias-label-tertiary)}.zjup-W_menu{flex:none;align-self:stretch;display:flex}";
		const tagId$1 = "@deepseek-ai/dsh-client-ui-sidebar-terminal/TerminalGuide.module.css";
		if (typeof document !== "undefined" && document.querySelector("style[data-plugin-css=" + JSON.stringify(tagId$1) + "]") === null) {
			const tag = document.createElement("style");
			tag.dataset.plugin = "@deepseek-ai/dsh-client-ui-sidebar-terminal";
			tag.dataset.pluginCss = tagId$1;
			tag.textContent = css$1;
			document.head.appendChild(tag);
		}
		var TerminalGuide_module_css_default = {
			"description": "zjup-W_description",
			"entry": "zjup-W_entry",
			"icon": "zjup-W_icon",
			"main": "zjup-W_main",
			"menu": "zjup-W_menu",
			"text": "zjup-W_text",
			"title": "zjup-W_title",
			"trigger": "zjup-W_trigger"
		};
		//#endregion
		//#region lib/types/client/TerminalGuide.js
		/** Shell launch menu owned by the terminal provider's guide entry. */
		/**
		* Open the remembered shell from the card or choose another shell from its menu.
		* @param props - guide copy, enclosing tab actions and cancellable discovery.
		* @returns separate launch and menu buttons within one guide card.
		*/
		function TerminalGuide({ title, description, kind, useTabInfo, loadShells, selectShell, t }) {
			const { tab } = useTabInfo();
			const [open, setOpen] = (0, react.useState)(false);
			const [attempt, setAttempt] = (0, react.useState)(0);
			const [state, setState] = (0, react.useState)({ phase: "loading" });
			(0, react.useEffect)(() => {
				if (!open) return;
				const lifetime = new AbortController();
				loadShells(lifetime.signal).then((choices) => {
					if (!lifetime.signal.aborted) setState({
						phase: "ready",
						choices
					});
				}, (error) => {
					if (!lifetime.signal.aborted) setState({
						phase: "failed",
						message: error instanceof Error ? error.message : String(error)
					});
				});
				return () => {
					lifetime.abort();
				};
			}, [
				open,
				attempt,
				loadShells
			]);
			const items = state.phase === "ready" ? state.choices.shells.map((shell) => ({
				id: shell.path,
				label: shell.name
			})) : state.phase === "loading" ? [{
				id: "loading",
				label: t("shellLoading"),
				disabled: true
			}] : [{
				id: "error",
				label: t("failed", { message: state.message }),
				disabled: true
			}, {
				id: "retry",
				label: t("retry")
			}];
			return (0, react_jsx_runtime.jsxs)("div", {
				className: TerminalGuide_module_css_default.entry,
				"data-sidebar-right-guide-entry": kind,
				children: [(0, react_jsx_runtime.jsxs)(_deepseek_ai_dsh_client_ui_primitives.Button, {
					variant: "ghost",
					className: TerminalGuide_module_css_default.main,
					onClick: () => {
						tab.actions.openTab("terminal", { replaceTab: true });
					},
					children: [(0, react_jsx_runtime.jsx)(TerminalGuideIcon, {
						size: description === void 0 ? 22 : 26,
						className: TerminalGuide_module_css_default.icon
					}), (0, react_jsx_runtime.jsxs)("span", {
						className: TerminalGuide_module_css_default.text,
						children: [(0, react_jsx_runtime.jsx)("span", {
							className: TerminalGuide_module_css_default.title,
							children: title
						}), description !== void 0 && (0, react_jsx_runtime.jsx)("span", {
							className: TerminalGuide_module_css_default.description,
							children: description
						})]
					})]
				}), (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.Menu, {
					open,
					portal: true,
					autoFocus: true,
					align: "end",
					className: TerminalGuide_module_css_default.menu,
					items: items.length === 0 ? [{
						id: "empty",
						label: t("shellEmpty"),
						disabled: true
					}] : items,
					selectedId: state.phase === "ready" ? state.choices.selectedShell : void 0,
					onClose: () => {
						setOpen(false);
					},
					onSelect: (path) => {
						if (state.phase === "failed") {
							setState({ phase: "loading" });
							setAttempt((value) => value + 1);
							return;
						}
						selectShell(path);
						setOpen(false);
						tab.actions.openTab("terminal", {
							replaceTab: true,
							params: { shellPath: path }
						});
					},
					anchor: (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.Button, {
						variant: "ghost",
						className: TerminalGuide_module_css_default.trigger,
						"aria-label": t("shell"),
						"aria-haspopup": "menu",
						"aria-expanded": open,
						onClick: () => {
							setState({ phase: "loading" });
							setOpen((value) => !value);
						},
						children: (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.IconChevronDownOutlineRegular, {})
					})
				})]
			});
		}
		//#endregion
		//#region lib/types/client/LazyTerminalBody.js
		/** Load xterm only after a terminal body is mounted. */
		const LoadedTerminalBody = (0, react.lazy)(async () => ({ default: (await require.async("./client.terminal.js")).TerminalBody }));
		/**
		* Suspend while the package-local terminal chunk arrives.
		* @param props - Terminal body props supplied by the sidebar slot.
		* @returns the deferred terminal renderer.
		*/
		function LazyTerminalBody(props) {
			return (0, react_jsx_runtime.jsx)(react.Suspense, {
				fallback: null,
				children: (0, react_jsx_runtime.jsx)(LoadedTerminalBody, { ...props })
			});
		}
		//#endregion
		//#region \0dsh-css:/home/runner/work/deepseek-harness/deepseek-harness/packages/client/ui-sidebar-terminal/src/client/TerminalTitle.module.css.mjs
		const css = ".ymsBma_title{text-overflow:ellipsis;white-space:nowrap;min-width:0;overflow:hidden}.ymsBma_name{width:120px;min-width:48px;max-width:100%;color:inherit;font:inherit;background:var(--dsw-alias-bg-l1);border:.5px solid var(--dsw-alias-border-l3);border-radius:4px;outline:none;padding:0 4px}";
		const tagId = "@deepseek-ai/dsh-client-ui-sidebar-terminal/TerminalTitle.module.css";
		if (typeof document !== "undefined" && document.querySelector("style[data-plugin-css=" + JSON.stringify(tagId) + "]") === null) {
			const tag = document.createElement("style");
			tag.dataset.plugin = "@deepseek-ai/dsh-client-ui-sidebar-terminal";
			tag.dataset.pluginCss = tagId;
			tag.textContent = css;
			document.head.appendChild(tag);
		}
		var TerminalTitle_module_css_default = {
			"name": "ymsBma_name",
			"title": "ymsBma_title"
		};
		//#endregion
		//#region lib/types/client/TerminalTitle.js
		/** Live terminal names in docked and floating tab chrome. */
		/**
		* Render the terminal name, editable in place on double-click.
		* @param props - sidebar occurrence, terminal model and localized copy.
		* @returns the terminal icon and current name or its editor.
		*/
		function TerminalTitle({ useTabInfo, useTerminal, view, t }) {
			const { tab } = useTabInfo();
			const title = useTerminal(tab.id, (state) => state?.info?.title ?? state?.title) ?? tab.title;
			const [editing, setEditing] = (0, react.useState)(false);
			const input = (0, react.useRef)(null);
			const label = (0, react.useRef)(null);
			const cancelled = (0, react.useRef)(false);
			(0, react.useLayoutEffect)(() => {
				if (editing) return;
				const chip = label.current?.closest("[data-dockkit-tab], [data-dockkit-float-grip]");
				const rename = (event) => {
					event.stopPropagation();
					cancelled.current = false;
					setEditing(true);
				};
				chip?.addEventListener("dblclick", rename);
				return () => {
					chip?.removeEventListener("dblclick", rename);
				};
			}, [editing]);
			(0, react.useLayoutEffect)(() => {
				if (!editing) return;
				input.current?.focus();
				input.current?.select();
			}, [editing]);
			return (0, react_jsx_runtime.jsxs)(react_jsx_runtime.Fragment, { children: [(0, react_jsx_runtime.jsx)(TerminalIcon, {}), editing ? (0, react_jsx_runtime.jsx)("input", {
				ref: input,
				className: TerminalTitle_module_css_default.name,
				defaultValue: title,
				maxLength: 120,
				"aria-label": t("rename"),
				onPointerDown: (event) => {
					event.stopPropagation();
				},
				onClick: (event) => {
					event.stopPropagation();
				},
				onDoubleClick: (event) => {
					event.stopPropagation();
				},
				onBlur: (event) => {
					setEditing(false);
					const next = event.currentTarget.value.trim();
					if (!cancelled.current && next !== "" && next !== title) view(tab.id).rename(next);
				},
				onKeyDown: (event) => {
					event.stopPropagation();
					if (event.nativeEvent.isComposing || event.nativeEvent.keyCode === 229) return;
					if (event.key === "Escape") {
						cancelled.current = true;
						event.currentTarget.blur();
					} else if (event.key === "Enter") event.currentTarget.blur();
				}
			}) : (0, react_jsx_runtime.jsx)("span", {
				ref: label,
				className: TerminalTitle_module_css_default.title,
				children: title
			})] });
		}
		//#endregion
		//#region lib/types/client/locales.js
		/** Simplified Chinese terminal copy. */
		const zh = {
			recoveryFailed: "恢复终端失败：{message}",
			retryRecovery: "重试恢复终端",
			shell: "选择 Shell",
			shellLoading: "正在读取 Shell…",
			shellEmpty: "没有可用的 Shell",
			description: "在会话工作区运行命令",
			title: "终端",
			new: "新建终端",
			loading: "正在读取终端环境…",
			creating: "正在启动…",
			connecting: "正在连接…",
			disconnected: "连接已断开。",
			reconnect: "重新连接",
			readonly: "此页面当前只读。",
			control: "接管输入",
			closed: "终端已关闭。",
			exited: "进程已退出（{code}）",
			failed: "终端错误：{message}",
			rename: "终端名称",
			unavailable: "不可用",
			retry: "重试",
			cleanupFailed: "终端「{title}」未能结束：{message}",
			missingTerminal: "此终端已不存在，请新建终端。",
			inputFull: "输入缓冲区已满，请重新连接后重试。",
			attachmentEnded: "终端连接已结束，请重新连接。",
			invalidOutput: "终端画面传输异常，请重新连接。",
			terminalLimit: "终端数量已达上限，请关闭不用的终端后重试。已退出的终端也计入数量。"
		};
		/** English terminal copy. */
		const en = {
			recoveryFailed: "Terminal recovery failed: {message}",
			retryRecovery: "Retry terminal recovery",
			shell: "Choose shell",
			shellLoading: "Loading shells…",
			shellEmpty: "No shells available",
			description: "Run commands in the Session workspace",
			title: "Terminal",
			new: "New terminal",
			loading: "Reading terminal environment…",
			creating: "Starting…",
			connecting: "Connecting…",
			disconnected: "Disconnected.",
			reconnect: "Reconnect",
			readonly: "This view is read-only.",
			control: "Take control",
			closed: "Terminal closed.",
			exited: "Process exited ({code})",
			failed: "Terminal error: {message}",
			rename: "Terminal name",
			unavailable: "Unavailable",
			retry: "Retry",
			cleanupFailed: "Terminal “{title}” could not be ended: {message}",
			missingTerminal: "This terminal no longer exists. Open a new terminal.",
			inputFull: "The input buffer is full. Reconnect and try again.",
			attachmentEnded: "The terminal connection ended. Reconnect to continue.",
			invalidOutput: "The terminal screen could not be received. Reconnect to recover it.",
			terminalLimit: "The terminal limit has been reached. Close unused terminals and try again. Exited terminals also count toward the limit."
		};
		//#endregion
		//#region lib/types/client/index.js
		/** Services needed by the terminal's two sidebar seats. */
		const inject = [
			"slots",
			"locale",
			"sidebarRight",
			"sidebarRightTabs",
			"webTerminals",
			"theme"
		];
		/**
		* Register the terminal type, observable views and background process cleanup.
		* @param ctx - Client root Context with sidebar and terminal services.
		*/
		function apply(ctx) {
			ctx.effect(() => {
				const sync = () => {
					ctx.webTerminals.retainTabs(ctx.sidebarRight.openTabs.getSnapshot().filter((tab) => tab.kind === "terminal"));
				};
				const unsubscribe = ctx.sidebarRight.openTabs.subscribe(sync);
				sync();
				return () => {
					unsubscribe();
					ctx.webTerminals.retainTabs([]);
				};
			}, "ui-sidebar-terminal.window-holds");
			const target = (sessionId, key) => ctx.sidebarRight.tabDomain.occurrence(sessionId, { id: key }).navigation.getSnapshot().params;
			const terminalId = (sessionId, key) => {
				const params = target(sessionId, key);
				return params !== void 0 && "terminalId" in params ? params.terminalId : void 0;
			};
			const view = (sessionId, key) => {
				const params = target(sessionId, key);
				const contentId = ctx.sidebarRight.tabDomain.occurrence(sessionId, { id: key }).navigation.getSnapshot().address;
				return ctx.webTerminals.view(sessionId, key, contentId, terminalId(sessionId, key), params !== void 0 && "shellPath" in params ? params.shellPath : void 0);
			};
			const namespace = "sidebarTerminal";
			const id = "@deepseek-ai/dsh-client-ui-sidebar-terminal";
			const t = ctx.locale.bind(namespace);
			ctx.effect(() => ctx.locale.register(namespace, {
				zh,
				en
			}), "ui-sidebar-terminal.copy");
			ctx.effect(() => ctx.sidebarRightTabs.register({
				id,
				kind: "terminal",
				multiple: true,
				priority: "builtin",
				title: () => t("title"),
				guide: [{
					id: "new",
					order: 20,
					title: () => t("new"),
					description: () => t("description"),
					icon: TerminalGuideIcon
				}]
			}), "ui-sidebar-terminal.type");
			ctx.effect(() => ctx.sidebarRight.registerCloseHandler("terminal", (sessionId, tab) => {
				ctx.webTerminals.close(sessionId, tab.id, tab.contentId, terminalId(sessionId, tab.id));
			}), "ui-sidebar-terminal.close");
			const inject = (sessionId) => ({
				view: (key) => view(sessionId, key),
				keyedHooks: { terminal: (key) => view(sessionId, key).state }
			});
			const theme = {
				getSnapshot: () => ctx.theme.getTheme(),
				subscribe: (listener) => ctx.on("theme/change", listener)
			};
			ctx.effect(() => ctx.slots.inject("sidebar.right.tab.guide.entry", () => ctx.slots.register({
				name: "sidebar.right.tab.guide.entry",
				key: id,
				locale: namespace,
				inject: (sessionId) => ({
					loadShells: (signal) => ctx.webTerminals.launchShells(sessionId, signal),
					selectShell: (path) => {
						ctx.webTerminals.selectShell(path);
					}
				})
			}, TerminalGuide)), "ui-sidebar-terminal.guide");
			ctx.effect(() => ctx.slots.inject("sidebar.right.pane.tab", () => ctx.slots.register({
				name: "sidebar.right.pane.tab",
				key: id,
				locale: namespace,
				inject: (sessionId) => ({
					...inject(sessionId),
					hooks: { theme }
				})
			}, LazyTerminalBody)), "ui-sidebar-terminal.body");
			ctx.effect(() => ctx.slots.inject("sidebar.right.pane.tab.title", () => ctx.slots.register({
				name: "sidebar.right.pane.tab.title",
				key: id,
				locale: namespace,
				inject
			}, TerminalTitle)), "ui-sidebar-terminal.title");
		}
		//#endregion
		exports.apply = apply;
		exports.inject = inject;
		return module.exports;
	}
});

//# sourceMappingURL=client.js.map