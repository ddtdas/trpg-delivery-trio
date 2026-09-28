window.__ModuleLoader__.load({
	id: "@deepseek-ai/dsh-client-ui-settings-account",
	factory: (require) => {
		var module = { exports: {} };
		var exports = module.exports;
		Object.defineProperty(exports, Symbol.toStringTag, { value: "Module" });
		let react_jsx_runtime = require("react/jsx-runtime");
		let react = require("react");
		let _deepseek_ai_dsh_client_ui_primitives = require("@deepseek-ai/dsh-client-ui-primitives");
		let react_dom = require("react-dom");
		//#region ../../../vendor/cosmokit/src/misc.ts
		/** Return true when a value is `null` or `undefined`. */
		function isNullable(value) {
			return value === null || value === void 0;
		}
		/** Return true for non-array object values. */
		function isPlainObject(data) {
			return data && typeof data === "object" && !Array.isArray(data);
		}
		/** Filter object entries and return a new object. */
		function filterKeys(object, filter) {
			return Object.fromEntries(Object.entries(object).filter(([key, value]) => filter(key, value)));
		}
		/** Map object values while preserving the original key set. */
		function mapValues(object, transform) {
			return Object.fromEntries(Object.entries(object).map(([key, value]) => [key, transform(value, key)]));
		}
		/** Pick selected keys from an object, optionally including `undefined` values. */
		function pick(source, keys, forced) {
			if (!keys) return { ...source };
			const result = {};
			for (const key of keys) if (forced || source[key] !== void 0) result[key] = source[key];
			return result;
		}
		//#endregion
		//#region ../../../vendor/cosmokit/src/volatile.ts
		/** Shared config references used by schema validators and plugin runtimes. */
		const write = Symbol.for("cosmokit.volatile.write");
		function snapshot(value, ancestors = /* @__PURE__ */ new Set()) {
			if (typeof value === "function") throw new TypeError("volatile config cannot contain functions");
			if (value === null || typeof value !== "object") return value;
			if (ancestors.has(value)) throw new TypeError("volatile config cannot contain cycles");
			ancestors.add(value);
			try {
				if (Array.isArray(value)) return Object.freeze(value.map((item) => snapshot(item, ancestors)));
				if (Object.getPrototypeOf(value) !== Object.prototype && Object.getPrototypeOf(value) !== null) throw new TypeError("volatile config objects must be plain objects or arrays");
				return Object.freeze(Object.fromEntries(Object.entries(value).map(([key, item]) => [key, snapshot(item, ancestors)])));
			} finally {
				ancestors.delete(value);
			}
		}
		/**
		* Create a detached reference containing an immutable copy of the supplied data.
		* @param value - validated config data; class instances and functions are unsupported.
		* @returns a reference whose value is updated only by its owning runtime.
		*/
		function createVolatile(value) {
			let current = snapshot(value);
			return Object.freeze({
				get: () => current,
				[write]: (value) => {
					current = value;
				}
			});
		}
		/**
		* Identify references across ESM/CJS copies of the shared library.
		* @param value - a parsed config value.
		* @returns whether the value implements the shared reference protocol.
		*/
		function isVolatile(value) {
			return typeof value === "object" && value !== null && write in value;
		}
		//#endregion
		//#region ../../../vendor/cosmokit/src/types.ts
		/** Test values using `instanceof` with a `toStringTag` fallback. */
		function is(type, value) {
			if (arguments.length === 1) return (value) => is(type, value);
			return type in globalThis && value instanceof globalThis[type] || Object.prototype.toString.call(value).slice(8, -1) === type;
		}
		function isArrayBufferLike(value) {
			return is("ArrayBuffer", value) || is("SharedArrayBuffer", value);
		}
		function isArrayBufferSource(value) {
			return isArrayBufferLike(value) || ArrayBuffer.isView(value);
		}
		let Binary;
		(function(_Binary) {
			_Binary.is = isArrayBufferLike;
			_Binary.isSource = isArrayBufferSource;
			function fromSource(source) {
				if (ArrayBuffer.isView(source)) return source.buffer.slice(source.byteOffset, source.byteOffset + source.byteLength);
				else return source;
			}
			_Binary.fromSource = fromSource;
			function toBase64(source) {
				source = fromSource(source);
				if (typeof Buffer !== "undefined") return Buffer.from(source).toString("base64");
				let binary = "";
				const bytes = new Uint8Array(source);
				for (let i = 0; i < bytes.byteLength; i++) binary += String.fromCharCode(bytes[i]);
				return btoa(binary);
			}
			_Binary.toBase64 = toBase64;
			function fromBase64(source) {
				if (typeof Buffer !== "undefined") return fromSource(Buffer.from(source, "base64"));
				return Uint8Array.from(atob(source), (c) => c.charCodeAt(0));
			}
			_Binary.fromBase64 = fromBase64;
			function toHex(source) {
				source = fromSource(source);
				if (typeof Buffer !== "undefined") return Buffer.from(source).toString("hex");
				return Array.from(new Uint8Array(source), (byte) => byte.toString(16).padStart(2, "0")).join("");
			}
			_Binary.toHex = toHex;
			function fromHex(source) {
				if (typeof Buffer !== "undefined") return fromSource(Buffer.from(source, "hex"));
				const hex = source.length % 2 === 0 ? source : source.slice(0, source.length - 1);
				const buffer = [];
				for (let i = 0; i < hex.length; i += 2) buffer.push(parseInt(`${hex[i]}${hex[i + 1]}`, 16));
				return Uint8Array.from(buffer).buffer;
			}
			_Binary.fromHex = fromHex;
		})(Binary || (Binary = {}));
		Binary.fromBase64;
		Binary.toBase64;
		Binary.fromHex;
		Binary.toHex;
		/** Deep-clone common JavaScript values while preserving prototypes and cycles. */
		function clone(source, refs = /* @__PURE__ */ new Map()) {
			if (!source || typeof source !== "object") return source;
			if (is("Date", source)) return new Date(source.valueOf());
			if (is("RegExp", source)) return new RegExp(source.source, source.flags);
			if (isArrayBufferLike(source)) return source.slice(0);
			if (ArrayBuffer.isView(source)) return source.buffer.slice(source.byteOffset, source.byteOffset + source.byteLength);
			const cached = refs.get(source);
			if (cached) return cached;
			if (Array.isArray(source)) {
				const result = [];
				refs.set(source, result);
				source.forEach((value, index) => {
					result[index] = Reflect.apply(clone, null, [value, refs]);
				});
				return result;
			}
			const result = Object.create(Object.getPrototypeOf(source));
			refs.set(source, result);
			for (const key of Reflect.ownKeys(source)) {
				const descriptor = { ...Reflect.getOwnPropertyDescriptor(source, key) };
				if ("value" in descriptor) descriptor.value = Reflect.apply(clone, null, [descriptor.value, refs]);
				Reflect.defineProperty(result, key, descriptor);
			}
			return result;
		}
		/**
		* Compare values recursively, treating two volatile references as equal regardless of value.
		* Strict comparison distinguishes null/undefined, treats opaque objects by identity,
		* compares URLs by normalized href, treats array holes as undefined, and considers distinct cyclic structures unequal.
		* @param a - first value.
		* @param b - second value.
		* @param strict - whether to require strict data equality outside volatile references.
		* @returns whether the values compare equal.
		*/
		function deepEqual(a, b, strict) {
			const ancestors = /* @__PURE__ */ new Set();
			function compare(a, b) {
				if (a === b) return true;
				if (isVolatile(a) || isVolatile(b)) return isVolatile(a) && isVolatile(b);
				if (!strict && isNullable(a) && isNullable(b)) return true;
				if (typeof a !== typeof b || typeof a !== "object" || !a || !b) return false;
				if (ancestors.has(a)) return false;
				function check(test, then) {
					return test(a) ? test(b) ? then(a, b) : false : test(b) ? false : void 0;
				}
				ancestors.add(a);
				try {
					return check(Array.isArray, (a, b) => {
						if (a.length !== b.length) return false;
						for (let index = 0; index < a.length; index++) if (!compare(a[index], b[index])) return false;
						return true;
					}) ?? check(is("Date"), (a, b) => a.valueOf() === b.valueOf()) ?? check(is("URL"), (a, b) => a.href === b.href) ?? check(is("RegExp"), (a, b) => a.source === b.source && a.flags === b.flags) ?? check(isArrayBufferLike, (a, b) => {
						if (a.byteLength !== b.byteLength) return false;
						const viewA = new Uint8Array(a);
						const viewB = new Uint8Array(b);
						for (let i = 0; i < viewA.length; i++) if (viewA[i] !== viewB[i]) return false;
						return true;
					}) ?? ((!strict || [a, b].every((value) => Object.getPrototypeOf(value) === Object.prototype || Object.getPrototypeOf(value) === null)) && Object.keys({
						...a,
						...b
					}).every((key) => compare(a[key], b[key])));
				} finally {
					ancestors.delete(a);
				}
			}
			return compare(a, b);
		}
		//#endregion
		//#region ../../../vendor/cosmokit/src/time.ts
		let Time;
		(function(_Time) {
			_Time.millisecond = 1;
			const second = _Time.second = 1e3;
			const minute = _Time.minute = second * 60;
			const hour = _Time.hour = minute * 60;
			const day = _Time.day = hour * 24;
			const week = _Time.week = day * 7;
			let timezoneOffset = (/* @__PURE__ */ new Date()).getTimezoneOffset();
			function setTimezoneOffset(offset) {
				timezoneOffset = offset;
			}
			_Time.setTimezoneOffset = setTimezoneOffset;
			function getTimezoneOffset() {
				return timezoneOffset;
			}
			_Time.getTimezoneOffset = getTimezoneOffset;
			function getDateNumber(date = /* @__PURE__ */ new Date(), offset) {
				if (typeof date === "number") date = new Date(date);
				if (offset === void 0) offset = timezoneOffset;
				return Math.floor((date.valueOf() / minute - offset) / 1440);
			}
			_Time.getDateNumber = getDateNumber;
			function fromDateNumber(value, offset) {
				const date = new Date(value * day);
				if (offset === void 0) offset = timezoneOffset;
				return new Date(+date + offset * minute);
			}
			_Time.fromDateNumber = fromDateNumber;
			const numeric = /\d+(?:\.\d+)?/.source;
			const timeRegExp = new RegExp(`^${[
				"w(?:eek(?:s)?)?",
				"d(?:ay(?:s)?)?",
				"h(?:our(?:s)?)?",
				"m(?:in(?:ute)?(?:s)?)?",
				"s(?:ec(?:ond)?(?:s)?)?"
			].map((unit) => `(${numeric}${unit})?`).join("")}$`);
			function parseTime(source) {
				const capture = timeRegExp.exec(source);
				if (!capture) return 0;
				return (parseFloat(capture[1]) * week || 0) + (parseFloat(capture[2]) * day || 0) + (parseFloat(capture[3]) * hour || 0) + (parseFloat(capture[4]) * minute || 0) + (parseFloat(capture[5]) * second || 0);
			}
			_Time.parseTime = parseTime;
			function parseDate(date) {
				const parsed = parseTime(date);
				if (parsed) date = Date.now() + parsed;
				else if (/^\d{1,2}(:\d{1,2}){1,2}$/.test(date)) date = `${(/* @__PURE__ */ new Date()).toLocaleDateString()}-${date}`;
				else if (/^\d{1,2}-\d{1,2}-\d{1,2}(:\d{1,2}){1,2}$/.test(date)) date = `${(/* @__PURE__ */ new Date()).getFullYear()}-${date}`;
				return date ? new Date(date) : /* @__PURE__ */ new Date();
			}
			_Time.parseDate = parseDate;
			function format(ms) {
				const abs = Math.abs(ms);
				if (abs >= day - hour / 2) return Math.round(ms / day) + "d";
				else if (abs >= hour - minute / 2) return Math.round(ms / hour) + "h";
				else if (abs >= minute - second / 2) return Math.round(ms / minute) + "m";
				else if (abs >= second) return Math.round(ms / second) + "s";
				return ms + "ms";
			}
			_Time.format = format;
			function toDigits(source, length = 2) {
				return source.toString().padStart(length, "0");
			}
			_Time.toDigits = toDigits;
			function template(template, time = /* @__PURE__ */ new Date()) {
				return template.replace("yyyy", time.getFullYear().toString()).replace("yy", time.getFullYear().toString().slice(2)).replace("MM", toDigits(time.getMonth() + 1)).replace("dd", toDigits(time.getDate())).replace("hh", toDigits(time.getHours())).replace("mm", toDigits(time.getMinutes())).replace("ss", toDigits(time.getSeconds())).replace("SSS", toDigits(time.getMilliseconds(), 3));
			}
			_Time.template = template;
		})(Time || (Time = {}));
		//#endregion
		//#region ../../../vendor/schemastery/src/index.ts
		const kSchema = Symbol.for("schemastery");
		const kValidationError = Symbol.for("ValidationError");
		globalThis.__schemastery_index__ ??= 0;
		globalThis.__schemastery_refs__ = void 0;
		var ValidationError = class extends TypeError {
			options;
			name = "ValidationError";
			constructor(message, options) {
				let prefix = "$";
				for (const segment of options.path || []) if (typeof segment === "string") prefix += "." + segment;
				else if (typeof segment === "number") prefix += "[" + segment + "]";
				else if (typeof segment === "symbol") prefix += `[Symbol(${segment.toString()})]`;
				if (prefix.startsWith(".")) prefix = prefix.slice(1);
				super((prefix === "$" ? "" : `${prefix} `) + message);
				this.options = options;
			}
			static is(error) {
				return !!error?.[kValidationError];
			}
		};
		Object.defineProperty(ValidationError.prototype, kValidationError, { value: true });
		const Schema = function(options) {
			const schema = function(data, options = {}) {
				return Schema.resolve(data, schema, options)[0];
			};
			if (options.refs) {
				const refs = mapValues(options.refs, (options) => new Schema(options));
				const getRef = (uid) => refs[uid];
				for (const key in refs) {
					const options = refs[key];
					options.sKey = getRef(options.sKey);
					options.inner = getRef(options.inner);
					options.list = options.list && options.list.map(getRef);
					options.dict = options.dict && mapValues(options.dict, getRef);
				}
				return refs[options.uid];
			}
			Object.assign(schema, options);
			if (typeof schema.callback === "string") try {
				schema.callback = new Function("return " + schema.callback)();
			} catch {}
			Object.defineProperty(schema, "uid", { value: globalThis.__schemastery_index__++ });
			Object.setPrototypeOf(schema, Schema.prototype);
			schema.meta ||= {};
			schema.toString = schema.toString.bind(schema);
			return schema;
		};
		Schema.prototype = Object.create(Function.prototype);
		Schema.prototype[kSchema] = true;
		Object.defineProperty(Schema.prototype, "~standard", { get() {
			return {
				version: 1,
				vendor: "schemastery",
				validate: (value) => {
					try {
						return { value: Schema.resolve(value, this, {})[0] };
					} catch (error) {
						if (ValidationError.is(error)) return { issues: [{
							message: error.message,
							path: error.options.path
						}] };
						throw error;
					}
				}
			};
		} });
		Schema.ValidationError = ValidationError;
		Schema.prototype.toJSON = function toJSON() {
			if (globalThis.__schemastery_refs__) {
				globalThis.__schemastery_refs__[this.uid] ??= JSON.parse(JSON.stringify({ ...this }));
				return this.uid;
			}
			globalThis.__schemastery_refs__ = { [this.uid]: { ...this } };
			globalThis.__schemastery_refs__[this.uid] = JSON.parse(JSON.stringify({ ...this }));
			const result = {
				uid: this.uid,
				refs: globalThis.__schemastery_refs__
			};
			globalThis.__schemastery_refs__ = void 0;
			return result;
		};
		Schema.prototype.set = function set(key, value) {
			this.dict[key] = value;
			return this;
		};
		Schema.prototype.push = function push(value) {
			this.list.push(value);
			return this;
		};
		function mergeDesc(original, messages) {
			const result = typeof original === "string" ? { "": original } : { ...original };
			for (const locale in messages) {
				const value = messages[locale];
				if (value?.$description || value?.$desc) result[locale] = value.$description || value.$desc;
				else if (typeof value === "string") result[locale] = value;
			}
			return result;
		}
		function getInner(value) {
			return value?.$value ?? value?.$inner;
		}
		function extractKeys(data) {
			return filterKeys(data ?? {}, (key) => !key.startsWith("$"));
		}
		Schema.prototype.i18n = function i18n(messages) {
			const schema = Schema(this);
			const desc = mergeDesc(schema.meta.description, messages);
			if (Object.keys(desc).length) schema.meta.description = desc;
			if (schema.dict) schema.dict = mapValues(schema.dict, (inner, key) => {
				return inner.i18n(mapValues(messages, (data) => getInner(data)?.[key] ?? data?.[key]));
			});
			if (schema.list) schema.list = schema.list.map((inner, index) => {
				return inner.i18n(mapValues(messages, (data = {}) => {
					if (Array.isArray(getInner(data))) return getInner(data)[index];
					if (Array.isArray(data)) return data[index];
					return extractKeys(data);
				}));
			});
			if (schema.inner) schema.inner = schema.inner.i18n(mapValues(messages, (data) => {
				if (getInner(data)) return getInner(data);
				return extractKeys(data);
			}));
			if (schema.sKey) schema.sKey = schema.sKey.i18n(mapValues(messages, (data) => data?.$key));
			return schema;
		};
		Schema.prototype.extra = function extra(key, value) {
			const schema = Schema(this);
			schema.meta = {
				...schema.meta,
				[key]: value
			};
			return schema;
		};
		for (const key of [
			"required",
			"disabled",
			"collapse",
			"hidden",
			"loose"
		]) Object.assign(Schema.prototype, { [key](value = true) {
			const schema = Schema(this);
			schema.meta = {
				...schema.meta,
				[key]: value
			};
			return schema;
		} });
		Schema.prototype.deprecated = function deprecated() {
			const schema = Schema(this);
			schema.meta.badges ||= [];
			schema.meta.badges.push({
				text: "deprecated",
				type: "danger"
			});
			return schema;
		};
		Schema.prototype.experimental = function experimental() {
			const schema = Schema(this);
			schema.meta.badges ||= [];
			schema.meta.badges.push({
				text: "experimental",
				type: "warning"
			});
			return schema;
		};
		Schema.prototype.pattern = function pattern(regexp) {
			const schema = Schema(this);
			const pattern = pick(regexp, ["source", "flags"]);
			schema.meta = {
				...schema.meta,
				pattern
			};
			return schema;
		};
		Schema.prototype.simplify = function simplify(value) {
			if (isVolatile(value)) value = value.get();
			if (deepEqual(value, this.meta.default, this.type === "dict")) return null;
			if (isNullable(value)) return value;
			if (this.type === "object" || this.type === "dict") {
				const result = {};
				for (const key in value) {
					const item = (this.type === "object" ? this.dict[key] : this.inner)?.simplify(value[key]);
					if (this.type === "dict" || !isNullable(item)) result[key] = item;
				}
				if (deepEqual(result, this.meta.default, this.type === "dict")) return null;
				return result;
			} else if (this.type === "array" || this.type === "tuple") {
				const result = [];
				value.forEach((value, index) => {
					const schema = this.type === "array" ? this.inner : this.list[index];
					const item = schema ? schema.simplify(value) : value;
					result.push(item);
				});
				return result;
			} else if (this.type === "intersect") {
				const result = {};
				for (const item of this.list) Object.assign(result, item.simplify(value));
				return result;
			} else if (this.type === "union") for (const schema of this.list) try {
				Schema.resolve(value, schema, {});
				return schema.simplify(value);
			} catch {}
			return value;
		};
		Schema.prototype.toString = function toString(inline) {
			return formatters[this.type]?.(this, inline) ?? `Schema<${this.type}>`;
		};
		Schema.prototype.role = function role(role, extra) {
			const schema = Schema(this);
			schema.meta = {
				...schema.meta,
				role,
				extra
			};
			return schema;
		};
		for (const key of [
			"default",
			"link",
			"comment",
			"description",
			"max",
			"min",
			"step"
		]) Object.assign(Schema.prototype, { [key](value) {
			const schema = Schema(this);
			schema.meta = {
				...schema.meta,
				[key]: value
			};
			return schema;
		} });
		Schema.prototype.volatile = function volatile() {
			if (this.meta.volatile) throw new TypeError("volatile schema is already wrapped");
			return this.extra("volatile", true);
		};
		const resolvers = {};
		const checkedVolatile = Symbol("checked-volatile-schema");
		function validateVolatileSchema(schema, path = [], blocked = false, seen = /* @__PURE__ */ new Map()) {
			const states = seen.get(schema) ?? /* @__PURE__ */ new Set();
			if (states.has(blocked)) return;
			states.add(blocked);
			seen.set(schema, states);
			if (schema.meta?.volatile && blocked) throw new ValidationError("volatile fields require a fixed object path without an enclosing volatile field", { path });
			const nested = blocked || !!schema.meta?.volatile;
			if (schema.dict) for (const [key, child] of Object.entries(schema.dict)) validateVolatileSchema(child, [...path, key], nested, seen);
			if (schema.sKey) validateVolatileSchema(schema.sKey, [...path, "<key>"], true, seen);
			if (schema.inner && (schema.type !== "lazy" || schema.inner[kSchema])) validateVolatileSchema(schema.inner, [...path, "*"], true, seen);
			if (schema.list) for (let index = 0; index < schema.list.length; index++) validateVolatileSchema(schema.list[index], [...path, String(index)], true, seen);
		}
		Schema.extend = function extend(type, resolve) {
			resolvers[type] = resolve;
		};
		Schema.resolve = function resolve(data, schema, options = {}, strict = false) {
			if (!schema) return [data];
			if (!options[checkedVolatile]) {
				validateVolatileSchema(schema, options.path);
				options = {
					...options,
					[checkedVolatile]: true
				};
			}
			if (schema.meta?.volatile) {
				const inner = Schema(schema);
				inner.meta = {
					...schema.meta,
					volatile: false
				};
				const [value, adapted] = Schema.resolve(data, inner, options, strict);
				try {
					return [createVolatile(value), adapted];
				} catch (error) {
					throw new ValidationError(error instanceof Error ? error.message : String(error), options);
				}
			}
			if (options.ignore?.(data, schema)) return [data];
			if (isNullable(data) && schema.type !== "lazy") {
				if (schema.meta.required) throw new ValidationError(`missing required value`, options);
				let current = schema;
				let fallback = schema.meta.default;
				while (current?.type === "intersect" && isNullable(fallback)) {
					current = current.list[0];
					fallback = current?.meta.default;
				}
				if (isNullable(fallback)) return [data];
				data = clone(fallback);
			}
			const callback = resolvers[schema.type];
			if (!callback) throw new ValidationError(`unsupported type "${schema.type}"`, options);
			try {
				return callback(data, schema, options, strict);
			} catch (error) {
				if (!schema.meta.loose) throw error;
				return [schema.meta.default];
			}
		};
		Schema.from = function from(source) {
			if (isNullable(source)) return Schema.any();
			else if ([
				"string",
				"number",
				"boolean"
			].includes(typeof source)) return Schema.const(source).required();
			else if (source[kSchema]) return source;
			else if (typeof source === "function") switch (source) {
				case String: return Schema.string().required();
				case Number: return Schema.number().required();
				case Boolean: return Schema.boolean().required();
				case Function: return Schema.function().required();
				default: return Schema.is(source).required();
			}
			else throw new TypeError(`cannot infer schema from ${source}`);
		};
		Schema.lazy = function lazy(builder) {
			const toJSON = () => {
				if (!schema.inner[kSchema]) {
					schema.inner = schema.builder();
					schema.inner.meta = {
						...schema.meta,
						...schema.inner.meta
					};
				}
				return schema.inner.toJSON();
			};
			const schema = new Schema({
				type: "lazy",
				builder,
				inner: { toJSON }
			});
			return schema;
		};
		Schema.natural = function natural() {
			return Schema.number().step(1).min(0);
		};
		Schema.percent = function percent() {
			return Schema.number().step(.01).min(0).max(1).role("slider");
		};
		Schema.date = function date() {
			return Schema.union([Schema.is(Date), Schema.transform(Schema.string().role("datetime"), (value, options) => {
				const date = new Date(value);
				if (isNaN(+date)) throw new ValidationError(`invalid date "${value}"`, options);
				return date;
			}, true)]);
		};
		Schema.regExp = function regExp(flag = "") {
			return Schema.union([Schema.is(RegExp), Schema.transform(Schema.string().role("regexp", { flag }), (value, options) => {
				try {
					return new RegExp(value, flag);
				} catch (e) {
					throw new ValidationError(e.message, options);
				}
			}, true)]);
		};
		Schema.arrayBuffer = function arrayBuffer(encoding) {
			return Schema.union([
				Schema.is(ArrayBuffer),
				Schema.is(SharedArrayBuffer),
				Schema.transform(Schema.any(), (value, options) => {
					if (Binary.isSource(value)) return Binary.fromSource(value);
					throw new ValidationError(`expected ArrayBufferSource but got ${value}`, options);
				}, true),
				...encoding ? [Schema.transform(Schema.string(), (value, options) => {
					try {
						return encoding === "base64" ? Binary.fromBase64(value) : Binary.fromHex(value);
					} catch (e) {
						throw new ValidationError(e.message, options);
					}
				}, true)] : []
			]);
		};
		Schema.extend("lazy", (data, schema, options, strict) => {
			if (!schema.inner[kSchema]) {
				schema.inner = schema.builder();
				schema.inner.meta = {
					...schema.meta,
					...schema.inner.meta
				};
				validateVolatileSchema(schema.inner, options.path, true);
			}
			return Schema.resolve(data, schema.inner, options, strict);
		});
		Schema.extend("any", (data) => {
			return [data];
		});
		Schema.extend("never", (data, _, options) => {
			throw new ValidationError(`expected nullable but got ${data}`, options);
		});
		Schema.extend("const", (data, { value }, options) => {
			if (deepEqual(data, value)) return [value];
			throw new ValidationError(`expected ${value} but got ${data}`, options);
		});
		function checkWithinRange(data, meta, description, options, skipMin = false) {
			const { max = Infinity, min = -Infinity } = meta;
			if (data > max) throw new ValidationError(`expected ${description} <= ${max} but got ${data}`, options);
			if (data < min && !skipMin) throw new ValidationError(`expected ${description} >= ${min} but got ${data}`, options);
		}
		Schema.extend("string", (data, { meta }, options) => {
			if (typeof data !== "string") throw new ValidationError(`expected string but got ${data}`, options);
			if (meta.pattern) {
				const regexp = new RegExp(meta.pattern.source, meta.pattern.flags);
				if (!regexp.test(data)) throw new ValidationError(`expect string to match regexp ${regexp}`, options);
			}
			checkWithinRange(data.length, meta, "string length", options);
			return [data];
		});
		function decimalShift(data, digits) {
			const str = data.toString();
			if (str.includes("e")) return data * Math.pow(10, digits);
			const index = str.indexOf(".");
			if (index === -1) return data * Math.pow(10, digits);
			const frac = str.slice(index + 1);
			const integer = str.slice(0, index);
			if (frac.length <= digits) return +(integer + frac.padEnd(digits, "0"));
			return +(integer + frac.slice(0, digits) + "." + frac.slice(digits));
		}
		function isMultipleOf(data, min, step) {
			step = Math.abs(step);
			if (!/^\d+\.\d+$/.test(step.toString())) return (data - min) % step === 0;
			const index = step.toString().indexOf(".");
			const digits = step.toString().slice(index + 1).length;
			return Math.abs(decimalShift(data, digits) - decimalShift(min, digits)) % decimalShift(step, digits) === 0;
		}
		Schema.extend("number", (data, { meta }, options) => {
			if (typeof data !== "number") throw new ValidationError(`expected number but got ${data}`, options);
			checkWithinRange(data, meta, "number", options);
			const { step } = meta;
			if (step && !isMultipleOf(data, meta.min ?? 0, step)) throw new ValidationError(`expected number multiple of ${step} but got ${data}`, options);
			return [data];
		});
		Schema.extend("boolean", (data, _, options) => {
			if (typeof data === "boolean") return [data];
			throw new ValidationError(`expected boolean but got ${data}`, options);
		});
		Schema.extend("bitset", (data, { bits, meta }, options) => {
			let value = 0, keys = [];
			if (typeof data === "number") {
				value = data;
				for (const key in bits) if (data & bits[key]) keys.push(key);
			} else if (Array.isArray(data)) {
				keys = data;
				for (const key of keys) {
					if (typeof key !== "string") throw new ValidationError(`expected string but got ${key}`, options);
					if (key in bits) value |= bits[key];
				}
			} else throw new ValidationError(`expected number or array but got ${data}`, options);
			if (value === meta.default) return [value];
			return [value, keys];
		});
		Schema.extend("function", (data, _, options) => {
			if (typeof data === "function") return [data];
			throw new ValidationError(`expected function but got ${data}`, options);
		});
		Schema.extend("is", (data, { constructor }, options) => {
			if (typeof constructor === "function") {
				if (data instanceof constructor) return [data];
				throw new ValidationError(`expected ${constructor.name} but got ${data}`, options);
			} else {
				if (isNullable(data)) throw new ValidationError(`expected ${constructor} but got ${data}`, options);
				let prototype = Object.getPrototypeOf(data);
				while (prototype) {
					if (prototype.constructor?.name === constructor) return [data];
					prototype = Object.getPrototypeOf(prototype);
				}
				throw new ValidationError(`expected ${constructor} but got ${data}`, options);
			}
		});
		function property(data, key, schema, options) {
			try {
				const [value, adapted] = Schema.resolve(data[key], schema, {
					...options,
					path: [...options.path || [], key]
				});
				if (adapted !== void 0) data[key] = adapted;
				return value;
			} catch (e) {
				if (!options?.autofix) throw e;
				delete data[key];
				return schema.meta.volatile ? createVolatile(schema.meta.default) : schema.meta.default;
			}
		}
		Schema.extend("array", (data, { inner, meta }, options) => {
			if (!Array.isArray(data)) throw new ValidationError(`expected array but got ${data}`, options);
			checkWithinRange(data.length, meta, "array length", options, !isNullable(inner.meta.default));
			return [data.map((_, index) => property(data, index, inner, options))];
		});
		Schema.extend("dict", (data, { inner, sKey }, options, strict) => {
			if (!isPlainObject(data)) throw new ValidationError(`expected object but got ${data}`, options);
			const result = {};
			for (const key in data) {
				let rKey;
				try {
					rKey = Schema.resolve(key, sKey, options)[0];
				} catch (error) {
					if (strict) continue;
					throw error;
				}
				result[rKey] = property(data, key, inner, options);
				data[rKey] = data[key];
				if (key !== rKey) delete data[key];
			}
			return [result];
		});
		Schema.extend("tuple", (data, { list }, options, strict) => {
			if (!Array.isArray(data)) throw new ValidationError(`expected array but got ${data}`, options);
			const result = list.map((inner, index) => property(data, index, inner, options));
			if (strict) return [result];
			result.push(...data.slice(list.length));
			return [result];
		});
		function merge(result, data) {
			for (const key in data) {
				if (key in result) continue;
				result[key] = data[key];
			}
		}
		Schema.extend("object", (data, { dict }, options, strict) => {
			if (!isPlainObject(data)) throw new ValidationError(`expected object but got ${data}`, options);
			const result = {};
			for (const key in dict) {
				const value = property(data, key, dict[key], options);
				if (!isNullable(value) || key in data) result[key] = value;
			}
			if (!strict) merge(result, data);
			return [result];
		});
		Schema.extend("union", (data, { list, toString }, options, strict) => {
			const messages = [];
			for (const inner of list) try {
				return Schema.resolve(data, inner, options, strict);
			} catch (error) {
				messages.push(error);
			}
			throw new ValidationError(`expected ${toString()} but got ${JSON.stringify(data)}`, options);
		});
		Schema.extend("intersect", (data, { list, toString }, options, strict) => {
			if (!list.length) return [data];
			let result;
			for (const inner of list) {
				const value = Schema.resolve(data, inner, options, true)[0];
				if (isNullable(value)) continue;
				if (isNullable(result)) result = value;
				else if (typeof result !== typeof value) throw new ValidationError(`expected ${toString()} but got ${JSON.stringify(data)}`, options);
				else if (typeof value === "object") merge(result ??= {}, value);
				else if (result !== value) throw new ValidationError(`expected ${toString()} but got ${JSON.stringify(data)}`, options);
			}
			if (!strict && isPlainObject(data)) merge(result, data);
			return [result];
		});
		Schema.extend("transform", (data, { inner, callback, preserve }, options) => {
			const [result, adapted = data] = Schema.resolve(data, inner, options, true);
			if (preserve) return [callback(result)];
			else return [callback(result), callback(adapted)];
		});
		const formatters = {};
		function defineMethod(name, keys, format) {
			formatters[name] = format;
			Object.assign(Schema, { [name](...args) {
				const schema = new Schema({ type: name });
				keys.forEach((key, index) => {
					switch (key) {
						case "sKey":
							schema.sKey = args[index] ?? Schema.string();
							break;
						case "inner":
							schema.inner = Schema.from(args[index]);
							break;
						case "list":
							schema.list = args[index].map(Schema.from);
							break;
						case "dict":
							schema.dict = mapValues(args[index], Schema.from);
							break;
						case "bits":
							schema.bits = {};
							for (const key in args[index]) {
								if (typeof args[index][key] !== "number") continue;
								schema.bits[key] = args[index][key];
							}
							break;
						case "callback": {
							const callback = schema.callback = args[index];
							callback["toJSON"] ||= () => callback.toString();
							break;
						}
						case "constructor": {
							const constructor = schema.constructor = args[index];
							if (typeof constructor === "function") constructor["toJSON"] ||= () => constructor["name"];
							break;
						}
						default: schema[key] = args[index];
					}
				});
				if (name === "object" || name === "dict") schema.meta.default = {};
				else if (name === "array" || name === "tuple") schema.meta.default = [];
				else if (name === "bitset") schema.meta.default = 0;
				return schema;
			} });
		}
		defineMethod("is", ["constructor"], ({ constructor }) => {
			if (typeof constructor === "function") return constructor.name;
			else return constructor;
		});
		defineMethod("any", [], () => "any");
		defineMethod("never", [], () => "never");
		defineMethod("const", ["value"], ({ value }) => typeof value === "string" ? JSON.stringify(value) : value);
		defineMethod("string", [], () => "string");
		defineMethod("number", [], () => "number");
		defineMethod("boolean", [], () => "boolean");
		defineMethod("bitset", ["bits"], () => "bitset");
		defineMethod("function", [], () => "function");
		defineMethod("array", ["inner"], ({ inner }) => `${inner.toString(true)}[]`);
		defineMethod("dict", ["inner", "sKey"], ({ inner, sKey }) => `{ [key: ${sKey.toString()}]: ${inner.toString()} }`);
		defineMethod("tuple", ["list"], ({ list }) => `[${list.map((inner) => inner.toString()).join(", ")}]`);
		defineMethod("object", ["dict"], ({ dict }) => {
			if (Object.keys(dict).length === 0) return "{}";
			return `{ ${Object.entries(dict).map(([key, inner]) => {
				return `${key}${inner.meta.required ? "" : "?"}: ${inner.toString()}`;
			}).join(", ")} }`;
		});
		defineMethod("union", ["list"], ({ list }, inline) => {
			const result = list.map(({ toString: format }) => format()).join(" | ");
			return inline ? `(${result})` : result;
		});
		defineMethod("intersect", ["list"], ({ list }) => {
			return `${list.map((inner) => inner.toString(true)).join(" & ")}`;
		});
		defineMethod("transform", [
			"inner",
			"callback",
			"preserve"
		], ({ inner }, isInner) => inner.toString(isInner));
		//#endregion
		//#region lib/types/contact-config.js
		/** Public questionnaire deployment options shared by Host and Client. */
		/** Validate public questionnaire options. */
		const Config = Schema.object({
			contactFormUrl: Schema.string().pattern(/^https:\/\/[^/\s]+\//).default("https://trtgsjkv6r.feishu.cn/share/base/form/shrcnlCoGElW7MQznGy9r3YYXcg"),
			contactSource: Schema.string().default("")
		});
		//#endregion
		//#region lib/types/client/contact-url.js
		/**
		* Build an external questionnaire URL without authentication credentials.
		* @param config - questionnaire destination and supported source option.
		* @param context - currently available build and browser environment.
		* @returns questionnaire URL with hidden, optionally prefilled context fields.
		*/
		function contactUrl(config, context) {
			const url = new URL(config.contactFormUrl);
			const ratio = Number.isFinite(context.pixelRatio) ? context.pixelRatio : 1;
			const width = Math.round(context.width * ratio);
			const height = Math.round(context.height * ratio);
			const fields = {
				source: config.contactSource,
				app_version: context.version,
				os_version: void 0,
				device_brand: void 0,
				device_model: void 0,
				app_locale: context.locale,
				screen_resolution: width > 0 && height > 0 ? `${width}x${height}` : void 0
			};
			for (const [name, value] of Object.entries(fields)) {
				url.searchParams.set(`hide_${name}`, "1");
				url.searchParams.delete(`prefill_${name}`);
				if (value) url.searchParams.set(`prefill_${name}`, value);
			}
			url.searchParams.delete("prefill_uid");
			url.searchParams.delete("hide_uid");
			return url.href;
		}
		//#endregion
		//#region lib/types/client/authorize-url.js
		/** Platform authorization links that carry the Desktop palette into the login page. */
		/**
		* Add the resolved Desktop palette to a Platform authorization link without
		* dropping any parameter the Host already put on it.
		* @param authorizeUrl - authorization URL of the current account attempt.
		* @param colorScheme - resolved scheme of the active Desktop theme.
		* @returns the authorization URL carrying `theme=light` or `theme=dark`.
		*/
		function authorizeUrlWithTheme(authorizeUrl, colorScheme) {
			const url = new URL(authorizeUrl);
			url.searchParams.set("theme", colorScheme);
			return url.href;
		}
		//#endregion
		//#region \0dsh-css:/home/runner/work/deepseek-harness/deepseek-harness/packages/client/ui-settings-account/src/client/SignInDialog.module.css.mjs
		const css$4 = "._76YFJG_dialog{user-select:none;box-sizing:border-box;border:.5px solid var(--dsw-alias-border-inverted)}._76YFJG_content{flex-direction:column;width:100%;display:flex}._76YFJG_header{justify-content:space-between;align-items:center;gap:8px;padding:22px 24px 12px;display:flex}._76YFJG_title{color:var(--dsw-alias-label-primary);margin:0;font-size:16px;font-weight:500;line-height:24px}._76YFJG_close{box-sizing:border-box;width:28px;height:28px;color:var(--dsw-alias-label-primary);cursor:pointer;background:0 0;border:0;border-radius:28px;flex:none;justify-content:center;align-items:center;padding:6px;display:inline-flex}._76YFJG_close:hover{background:var(--dsw-alias-interactive-bg-hover)}._76YFJG_actions{box-sizing:border-box;justify-content:flex-end;align-items:center;gap:8px;width:100%;padding:0 24px;display:flex}._76YFJG_primaryButton,._76YFJG_secondaryButton{box-sizing:border-box;border-radius:12px;min-width:72px;height:36px;font-size:14px;line-height:22px}._76YFJG_primaryButton{padding:0 16px;font-weight:500}._76YFJG_secondaryButton{border:.5px solid var(--dsw-alias-border-l2);padding:0 14px}._76YFJG_description{color:var(--dsw-alias-label-primary);margin:0;padding:0 24px;font-size:14px;line-height:22px}._76YFJG_link{color:inherit;font:inherit;cursor:pointer;background:0 0;border:0;padding:0;text-decoration:underline}._76YFJG_spinner{flex:none;animation:1s linear infinite _76YFJG_spin}._76YFJG_primaryButton:has(._76YFJG_spinner){opacity:1}@keyframes _76YFJG_spin{to{transform:rotate(360deg)}}@media (prefers-reduced-motion:reduce){._76YFJG_spinner{animation:none}}";
		const tagId$4 = "@deepseek-ai/dsh-client-ui-settings-account/SignInDialog.module.css";
		if (typeof document !== "undefined" && document.querySelector("style[data-plugin-css=" + JSON.stringify(tagId$4) + "]") === null) {
			const tag = document.createElement("style");
			tag.dataset.plugin = "@deepseek-ai/dsh-client-ui-settings-account";
			tag.dataset.pluginCss = tagId$4;
			tag.textContent = css$4;
			document.head.appendChild(tag);
		}
		var SignInDialog_module_css_default = {
			"actions": "_76YFJG_actions",
			"close": "_76YFJG_close",
			"content": "_76YFJG_content",
			"description": "_76YFJG_description",
			"dialog": "_76YFJG_dialog",
			"header": "_76YFJG_header",
			"link": "_76YFJG_link",
			"primaryButton": "_76YFJG_primaryButton",
			"secondaryButton": "_76YFJG_secondaryButton",
			"spin": "_76YFJG_spin",
			"spinner": "_76YFJG_spinner",
			"title": "_76YFJG_title"
		};
		//#endregion
		//#region lib/types/client/SignInDialog.js
		/** Account authorization dialog; errors allow retry after cancelling any active attempt. */
		/** @param props - safe account state, localized copy, and user actions. @returns login dialog. */
		function SignInDialog({ account, colorScheme, start, cancel, close, useApiKey, t }) {
			const [busy, setBusy] = (0, react.useState)(false);
			const [failed, setFailed] = (0, react.useState)(false);
			const [copyResult, setCopyResult] = (0, react.useState)(null);
			const attempt = account.view?.attempt;
			(0, react.useEffect)(() => {
				setCopyResult(null);
			}, [attempt?.id, attempt?.authorizeUrl]);
			(0, react.useEffect)(() => {
				if (copyResult === null) return;
				const timer = setTimeout(() => {
					setCopyResult(null);
				}, 2e3);
				return () => {
					clearTimeout(timer);
				};
			}, [copyResult]);
			const authorizeUrl = attempt?.authorizeUrl;
			const phase = attempt?.phase;
			const active = busy || phase === "initializing" || phase === "waiting-browser" || phase === "exchanging" || phase === "committing";
			const expired = phase === "expired";
			const error = failed || account.loginFailed || account.failed || phase === "failed";
			const waiting = active && !error;
			const committing = phase === "committing";
			(0, react.useEffect)(() => {
				if (account.view?.status === "credential-stored") close();
			}, [account.view?.status, close]);
			const run = async (action) => {
				setBusy(true);
				setFailed(false);
				try {
					await action();
				} catch {
					setFailed(true);
				} finally {
					setBusy(false);
				}
			};
			const dismiss = () => {
				if (committing || busy) return;
				if (active && attempt) run(async () => {
					await cancel(attempt.id);
					close();
				});
				else close();
			};
			const retry = async () => {
				if (active && attempt) await cancel(attempt.id);
				await start();
			};
			const copyLink = async (authorizeUrl) => {
				try {
					await navigator.clipboard.writeText(authorizeUrlWithTheme(authorizeUrl, colorScheme));
					setCopyResult({ messageKey: "copiedLink" });
				} catch {
					setCopyResult({ messageKey: "copyFailed" });
				}
			};
			const title = error ? t("failureTitle") : active ? t("browserTitle") : expired ? t("timeoutTitle") : t("loginTitle");
			return (0, react_jsx_runtime.jsxs)(_deepseek_ai_dsh_client_ui_primitives.Modal, {
				open: true,
				headless: true,
				title,
				onClose: dismiss,
				className: SignInDialog_module_css_default.dialog,
				children: [(0, react_jsx_runtime.jsxs)("div", {
					className: SignInDialog_module_css_default.content,
					children: [(0, react_jsx_runtime.jsxs)("div", {
						className: SignInDialog_module_css_default.header,
						children: [(0, react_jsx_runtime.jsx)("h2", {
							className: SignInDialog_module_css_default.title,
							children: title
						}), (0, react_jsx_runtime.jsx)("button", {
							type: "button",
							className: SignInDialog_module_css_default.close,
							"aria-label": t("close"),
							onClick: dismiss,
							children: (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.IconCloseOutlineRegular, { size: 14 })
						})]
					}), waiting ? (0, react_jsx_runtime.jsxs)("p", {
						className: SignInDialog_module_css_default.description,
						children: [
							t("browserPrompt"),
							(0, react_jsx_runtime.jsx)("button", {
								type: "button",
								className: SignInDialog_module_css_default.link,
								disabled: !authorizeUrl,
								onClick: authorizeUrl ? () => {
									copyLink(authorizeUrl);
								} : void 0,
								children: t(copyResult?.messageKey ?? "copyLink")
							}),
							t("browserDescription")
						]
					}) : (0, react_jsx_runtime.jsx)("p", {
						className: SignInDialog_module_css_default.description,
						children: error ? t("failed") : expired ? t("timeoutDescription") : t("loginDescription")
					})]
				}), (0, react_jsx_runtime.jsxs)("div", {
					className: SignInDialog_module_css_default.actions,
					children: [(0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.Button, {
						variant: "outline",
						className: SignInDialog_module_css_default.secondaryButton,
						disabled: committing || busy,
						onClick: active ? dismiss : useApiKey,
						children: t(active ? "cancel" : "addApiKey")
					}), (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.Button, {
						variant: "primary",
						className: SignInDialog_module_css_default.primaryButton,
						disabled: busy || committing || waiting || account.view === void 0,
						"aria-label": waiting ? t("waiting") : void 0,
						onClick: () => {
							run(retry);
						},
						children: waiting ? (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.IconLoadingOutlineRegular, { className: SignInDialog_module_css_default.spinner }) : t(expired || error ? "retry" : "signIn")
					})]
				})]
			});
		}
		//#endregion
		//#region lib/types/client/AccountOnboarding.js
		/** Account choice inside the model credential onboarding step. */
		/** @param props - onboarding completion, account state and actions. @returns account dialog while signed out. */
		function AccountOnboarding({ complete, useApiKey, useAccount, useTheme, setOnboarding, showLogin, start, cancel, t }) {
			const account = useAccount((value) => value);
			const colorScheme = useTheme((snapshot) => snapshot.active.colorScheme);
			(0, react.useEffect)(() => {
				setOnboarding(true);
				return () => {
					setOnboarding(false);
				};
			}, [setOnboarding]);
			(0, react.useEffect)(() => {
				if (account.view?.status === "credential-stored") complete();
			}, [account.view?.status, complete]);
			if (!account.view || account.view.status === "credential-stored") return null;
			return (0, react_jsx_runtime.jsx)(SignInDialog, {
				account,
				colorScheme,
				start,
				cancel,
				t,
				close: () => {
					showLogin(false);
					complete();
				},
				useApiKey: () => {
					showLogin(false);
					useApiKey();
				}
			});
		}
		//#endregion
		//#region lib/types/client/LogoutIcon.js
		/** Figma IcDsLogOutOutline16 glyph, stored inline for theme-aware rendering. */
		/** @returns the account menu logout glyph. */
		function LogoutIcon() {
			return (0, react_jsx_runtime.jsx)("span", {
				style: {
					width: 16,
					height: 16,
					position: "relative"
				},
				"aria-hidden": "true",
				children: (0, react_jsx_runtime.jsxs)("svg", {
					style: {
						position: "absolute",
						left: 1.168,
						top: 1.214
					},
					width: "13.664",
					height: "13.571",
					viewBox: "0 0 14 14",
					fill: "none",
					xmlns: "http://www.w3.org/2000/svg",
					children: [(0, react_jsx_runtime.jsx)("path", {
						d: "M3.9961 1.40039C3.37842 1.40039 2.96028 1.40039 2.63867 1.42871C2.32631 1.45627 2.17171 1.50666 2.06641 1.56543C1.85606 1.68288 1.68189 1.85605 1.56446 2.06641C1.50569 2.17173 1.45625 2.32627 1.42871 2.63867C1.40036 2.9603 1.39942 3.37827 1.39942 3.9961L1.39942 9.5752C1.39942 10.193 1.40036 10.611 1.42871 10.9326C1.45625 11.245 1.50569 11.3996 1.56445 11.5049C1.68188 11.7153 1.85605 11.8884 2.06641 12.0059C2.17171 12.0646 2.32631 12.115 2.63867 12.1426C2.96028 12.1709 3.37842 12.1709 3.9961 12.1709V13.5713C3.4033 13.5713 2.91297 13.5721 2.51563 13.5371C2.10906 13.5013 1.73277 13.4233 1.38379 13.2285C0.946838 12.9845 0.585697 12.6235 0.341799 12.1865C0.14725 11.8377 0.0700118 11.4621 0.0341815 11.0557C-0.000847399 10.6583 1.58129e-06 10.1681 1.85029e-06 9.5752L2.09416e-06 3.9961C1.83027e-06 3.40325 -0.000846367 2.91297 0.0341818 2.51563C0.0700164 2.10924 0.147239 1.73362 0.341799 1.38477C0.585703 0.947758 0.946825 0.586744 1.38379 0.342775C1.73277 0.148001 2.10906 0.0700381 2.51563 0.0341813C2.91297 -0.000823893 3.40331 1.37805e-06 3.9961 1.71712e-06L3.9961 1.40039Z",
						fill: "currentColor"
					}), (0, react_jsx_runtime.jsx)("path", {
						d: "M13.6426 6.51953C13.6705 6.6957 13.6705 6.8756 13.6426 7.05176C13.5902 7.38188 13.4302 7.64112 13.2539 7.86035C13.0857 8.06937 12.8546 8.29971 12.6006 8.55371L9.3086 11.8447L8.31836 10.8545L11.6104 7.56348C11.637 7.53681 11.6628 7.51104 11.6875 7.48633H3.74317V6.08594H11.6885C11.6635 6.06088 11.6374 6.03487 11.6104 6.00781L8.31836 2.7168L9.3086 1.72656L12.6006 5.01758C12.8547 5.27169 13.0857 5.50185 13.2539 5.71094C13.4303 5.93018 13.5902 6.18939 13.6426 6.51953Z",
						fill: "currentColor"
					})]
				})
			});
		}
		//#endregion
		//#region \0dsh-css:/home/runner/work/deepseek-harness/deepseek-harness/packages/client/ui-settings-account/src/client/AccountAvatar.module.css.mjs
		const css$3 = ".ZCYJYW_image{border-radius:inherit;object-fit:cover;width:100%;height:100%;display:block}";
		const tagId$3 = "@deepseek-ai/dsh-client-ui-settings-account/AccountAvatar.module.css";
		if (typeof document !== "undefined" && document.querySelector("style[data-plugin-css=" + JSON.stringify(tagId$3) + "]") === null) {
			const tag = document.createElement("style");
			tag.dataset.plugin = "@deepseek-ai/dsh-client-ui-settings-account";
			tag.dataset.pluginCss = tagId$3;
			tag.textContent = css$3;
			document.head.appendChild(tag);
		}
		var AccountAvatar_module_css_default = { "image": "ZCYJYW_image" };
		//#endregion
		//#region lib/types/client/AccountAvatar.js
		/** Shared account picture with an icon fallback for missing or unavailable images. */
		/**
		* Render a decorative avatar next to the account identity.
		* @param props - profile picture URL; absent while signed out or loading.
		* @returns picture or the default account icon.
		*/
		function AccountAvatar({ url }) {
			const [failedUrl, setFailedUrl] = (0, react.useState)();
			return url && url !== failedUrl ? (0, react_jsx_runtime.jsx)("img", {
				className: AccountAvatar_module_css_default.image,
				src: url,
				alt: "",
				referrerPolicy: "no-referrer",
				onError: () => {
					setFailedUrl(url);
				}
			}) : (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.IconUserOutlineMedium, { size: 16 });
		}
		//#endregion
		//#region \0dsh-css:/home/runner/work/deepseek-harness/deepseek-harness/packages/client/ui-settings-account/src/client/AccountMenu.module.css.mjs
		const css$2 = ".yHnPSG_root{flex:1;min-width:0}.yHnPSG_anchor{width:100%}.yHnPSG_trigger{user-select:none;width:100%;color:var(--dsw-alias-label-primary);font:inherit;cursor:pointer;background:0 0;border:0;border-radius:12px;align-items:center;gap:8px;padding:6px;font-size:14px;display:flex}.yHnPSG_trigger[data-collapsed=true]{box-sizing:border-box;justify-content:center;gap:0;width:36px;height:36px;padding:0}.yHnPSG_trigger:hover{background:var(--dsw-alias-interactive-bg-hover)}.yHnPSG_avatar{background:var(--dsw-alias-bg-skeleton);width:32px;height:32px;color:var(--dsw-alias-label-tertiary);border-radius:16px;flex:none;justify-content:center;align-items:center;display:flex}.yHnPSG_label{text-overflow:ellipsis;white-space:nowrap;overflow:hidden}.yHnPSG_error{color:var(--dsw-alias-state-error-primary);font-size:12px}";
		const tagId$2 = "@deepseek-ai/dsh-client-ui-settings-account/AccountMenu.module.css";
		if (typeof document !== "undefined" && document.querySelector("style[data-plugin-css=" + JSON.stringify(tagId$2) + "]") === null) {
			const tag = document.createElement("style");
			tag.dataset.plugin = "@deepseek-ai/dsh-client-ui-settings-account";
			tag.dataset.pluginCss = tagId$2;
			tag.textContent = css$2;
			document.head.appendChild(tag);
		}
		var AccountMenu_module_css_default = {
			"anchor": "yHnPSG_anchor",
			"avatar": "yHnPSG_avatar",
			"error": "yHnPSG_error",
			"label": "yHnPSG_label",
			"root": "yHnPSG_root",
			"trigger": "yHnPSG_trigger"
		};
		//#endregion
		//#region lib/types/client/AccountMenu.js
		/** Sidebar account launcher and locally authoritative sign-out action. */
		/** The signed-in label stays empty while the profile loads.
		* @param props - sidebar geometry, settings navigation and account operations.
		* @returns account menu launcher.
		*/
		function AccountMenu({ wide, openSettings, openOnboarding, useAccount, useTheme, signOut, contactUs, showLogin, start, cancel, t }) {
			const account = useAccount((state) => state);
			const colorScheme = useTheme((snapshot) => snapshot.active.colorScheme);
			const signedIn = account.view?.status === "credential-stored";
			const profile = account.details?.profile;
			const label = profile === void 0 ? null : profile.status === "ready" ? profile.value.name ?? profile.value.contact ?? t("signedIn") : t("signedIn");
			const [open, setOpen] = (0, react.useState)(false);
			const [busy, setBusy] = (0, react.useState)(false);
			const [logoutFailed, setLogoutFailed] = (0, react.useState)(false);
			const logout = async () => {
				setBusy(true);
				setLogoutFailed(false);
				try {
					await signOut();
					setOpen(false);
				} catch {
					setLogoutFailed(true);
				} finally {
					setBusy(false);
				}
			};
			const beginSignIn = () => {
				setOpen(false);
				start().catch(() => void 0);
			};
			return (0, react_jsx_runtime.jsxs)("div", {
				className: AccountMenu_module_css_default.root,
				children: [
					(0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.Menu, {
						open,
						side: "top",
						portal: true,
						autoFocus: true,
						className: AccountMenu_module_css_default.anchor,
						anchor: (0, react_jsx_runtime.jsxs)("button", {
							type: "button",
							className: AccountMenu_module_css_default.trigger,
							"data-collapsed": !wide,
							"aria-label": t("menu"),
							"aria-haspopup": "menu",
							"aria-expanded": open,
							onClick: () => {
								setOpen((value) => !value);
							},
							children: [(0, react_jsx_runtime.jsx)("span", {
								className: AccountMenu_module_css_default.avatar,
								children: (0, react_jsx_runtime.jsx)(AccountAvatar, { url: signedIn && profile?.status === "ready" ? profile.value.avatarUrl : null })
							}), wide && (0, react_jsx_runtime.jsx)("span", {
								className: AccountMenu_module_css_default.label,
								children: signedIn ? label : t("signedOut")
							})]
						}),
						items: [
							{
								id: "settings",
								label: t("settings"),
								icon: (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.IconSettingsOutlineMedium, { size: 16 })
							},
							{
								id: "contact",
								label: t("contactUs"),
								icon: (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.IconPaperPlaneOutlineMedium, { size: 16 })
							},
							...signedIn ? [{
								id: "signout",
								label: t("signOut"),
								icon: (0, react_jsx_runtime.jsx)(LogoutIcon, {}),
								disabled: busy
							}] : [{
								id: "signin",
								label: t("signIn"),
								icon: (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.IconUserOutlineMedium, { size: 16 })
							}]
						],
						onClose: () => {
							setOpen(false);
						},
						onSelect: (id) => {
							if (id === "settings") {
								setOpen(false);
								openSettings();
							} else if (id === "contact") {
								setOpen(false);
								contactUs();
							} else if (id === "signin") beginSignIn();
							else logout();
						}
					}),
					account.loginVisible && !account.onboarding && (0, react_jsx_runtime.jsx)(SignInDialog, {
						account,
						colorScheme,
						start,
						cancel,
						t,
						close: () => {
							showLogin(false);
						},
						useApiKey: () => {
							showLogin(false);
							openOnboarding("deepseek-official");
						}
					}),
					logoutFailed && (0, react_jsx_runtime.jsx)("span", {
						className: AccountMenu_module_css_default.error,
						role: "alert",
						children: t("failed")
					})
				]
			});
		}
		//#endregion
		//#region ../../../node_modules/.pnpm/big.js@7.0.1/node_modules/big.js/big.mjs
		/************************************** EDITABLE DEFAULTS *****************************************/
		var DP = 20, RM = 1, MAX_DP = 1e6, MAX_POWER = 1e6, NE = -7, PE = 21, STRICT = false, NAME = "[big.js] ", INVALID = NAME + "Invalid ", INVALID_DP = INVALID + "decimal places", INVALID_RM = INVALID + "rounding mode", DIV_BY_ZERO = NAME + "Division by zero", P = {}, UNDEFINED = void 0, NUMERIC = /^-?(\d+(\.\d*)?|\.\d+)(e[+-]?\d+)?$/i;
		function _Big_() {
			function Big(n) {
				var x = this;
				if (!(x instanceof Big)) return n === UNDEFINED && arguments.length === 0 ? _Big_() : new Big(n);
				if (n instanceof Big) {
					x.s = n.s;
					x.e = n.e;
					x.c = n.c.slice();
				} else {
					if (typeof n !== "string") {
						if (Big.strict === true && typeof n !== "bigint") throw TypeError(INVALID + "value");
						n = n === 0 && 1 / n < 0 ? "-0" : String(n);
					}
					parse(x, n);
				}
				x.constructor = Big;
			}
			Big.prototype = P;
			Big.DP = DP;
			Big.RM = RM;
			Big.NE = NE;
			Big.PE = PE;
			Big.strict = STRICT;
			Big.roundDown = 0;
			Big.roundHalfUp = 1;
			Big.roundHalfEven = 2;
			Big.roundUp = 3;
			return Big;
		}
		function parse(x, n) {
			var e, i, nl;
			if (!NUMERIC.test(n)) throw Error(INVALID + "number");
			x.s = n.charAt(0) == "-" ? (n = n.slice(1), -1) : 1;
			if ((e = n.indexOf(".")) > -1) n = n.replace(".", "");
			if ((i = n.search(/e/i)) > 0) {
				if (e < 0) e = i;
				e += +n.slice(i + 1);
				n = n.substring(0, i);
			} else if (e < 0) e = n.length;
			nl = n.length;
			for (i = 0; i < nl && n.charAt(i) == "0";) ++i;
			if (i == nl) x.c = [x.e = 0];
			else {
				for (; nl > 0 && n.charAt(--nl) == "0";);
				x.e = e - i - 1;
				x.c = [];
				for (e = 0; i <= nl;) x.c[e++] = +n.charAt(i++);
			}
			return x;
		}
		function round(x, sd, rm, more) {
			var xc = x.c;
			if (rm === UNDEFINED) rm = x.constructor.RM;
			if (rm !== 0 && rm !== 1 && rm !== 2 && rm !== 3) throw Error(INVALID_RM);
			if (sd < 1) {
				more = rm === 3 && (more || !!xc[0]) || sd === 0 && (rm === 1 && xc[0] >= 5 || rm === 2 && (xc[0] > 5 || xc[0] === 5 && (more || xc[1] !== UNDEFINED)));
				xc.length = 1;
				if (more) {
					x.e = x.e - sd + 1;
					xc[0] = 1;
				} else xc[0] = x.e = 0;
			} else if (sd < xc.length) {
				more = rm === 1 && xc[sd] >= 5 || rm === 2 && (xc[sd] > 5 || xc[sd] === 5 && (more || xc[sd + 1] !== UNDEFINED || xc[sd - 1] & 1)) || rm === 3 && (more || !!xc[0]);
				xc.length = sd;
				if (more) for (; ++xc[--sd] > 9;) {
					xc[sd] = 0;
					if (sd === 0) {
						++x.e;
						xc.unshift(1);
						break;
					}
				}
				for (sd = xc.length; !xc[--sd];) xc.pop();
			}
			return x;
		}
		function stringify(x, doExponential, isNonzero) {
			var e = x.e, s = x.c.join(""), n = s.length;
			if (doExponential) s = s.charAt(0) + (n > 1 ? "." + s.slice(1) : "") + (e < 0 ? "e" : "e+") + e;
			else if (e < 0) {
				for (; ++e;) s = "0" + s;
				s = "0." + s;
			} else if (e > 0) {
				if (++e > n) for (e -= n; e--;) s += "0";
				else if (e < n) s = s.slice(0, e) + "." + s.slice(e);
			} else if (n > 1) s = s.charAt(0) + "." + s.slice(1);
			return x.s < 0 && isNonzero ? "-" + s : s;
		}
		P.abs = function() {
			var x = new this.constructor(this);
			x.s = 1;
			return x;
		};
		P.cmp = function(y) {
			var isneg, x = this, xc = x.c, yc = (y = new x.constructor(y)).c, i = x.s, j = y.s, k = x.e, l = y.e;
			if (!xc[0] || !yc[0]) return !xc[0] ? !yc[0] ? 0 : -j : i;
			if (i != j) return i;
			isneg = i < 0;
			if (k != l) return k > l ^ isneg ? 1 : -1;
			j = (k = xc.length) < (l = yc.length) ? k : l;
			for (i = -1; ++i < j;) if (xc[i] != yc[i]) return xc[i] > yc[i] ^ isneg ? 1 : -1;
			return k == l ? 0 : k > l ^ isneg ? 1 : -1;
		};
		P.div = function(y) {
			var x = this, Big = x.constructor, a = x.c, b = (y = new Big(y)).c, k = x.s == y.s ? 1 : -1, dp = Big.DP;
			if (dp !== ~~dp || dp < 0 || dp > MAX_DP) throw Error(INVALID_DP);
			if (!b[0]) throw Error(DIV_BY_ZERO);
			if (!a[0]) {
				y.s = k;
				y.c = [y.e = 0];
				return y;
			}
			var bl, bt, n, cmp, ri, bz = b.slice(), ai = bl = b.length, al = a.length, r = a.slice(0, bl), rl = r.length, q = y, qc = q.c = [], qi = 0, p = dp + (q.e = x.e - y.e) + 1;
			q.s = k;
			k = p < 0 ? 0 : p;
			bz.unshift(0);
			for (; rl++ < bl;) r.push(0);
			do {
				for (n = 0; n < 10; n++) {
					if (bl != (rl = r.length)) cmp = bl > rl ? 1 : -1;
					else for (ri = -1, cmp = 0; ++ri < bl;) if (b[ri] != r[ri]) {
						cmp = b[ri] > r[ri] ? 1 : -1;
						break;
					}
					if (cmp < 0) {
						for (bt = rl == bl ? b : bz; rl;) {
							if (r[--rl] < bt[rl]) {
								ri = rl;
								for (; ri && !r[--ri];) r[ri] = 9;
								--r[ri];
								r[rl] += 10;
							}
							r[rl] -= bt[rl];
						}
						for (; !r[0];) r.shift();
					} else break;
				}
				qc[qi++] = cmp ? n : ++n;
				if (r[0] && cmp) r[rl] = a[ai] || 0;
				else r = [a[ai]];
			} while ((ai++ < al || r[0] !== UNDEFINED) && k--);
			if (!qc[0] && qi != 1) {
				qc.shift();
				q.e--;
				p--;
			}
			if (qi > p) round(q, p, Big.RM, r[0] !== UNDEFINED);
			return q;
		};
		P.eq = function(y) {
			return this.cmp(y) === 0;
		};
		P.gt = function(y) {
			return this.cmp(y) > 0;
		};
		P.gte = function(y) {
			return this.cmp(y) > -1;
		};
		P.lt = function(y) {
			return this.cmp(y) < 0;
		};
		P.lte = function(y) {
			return this.cmp(y) < 1;
		};
		P.minus = P.sub = function(y) {
			var i, j, t, xlty, x = this, Big = x.constructor, a = x.s, b = (y = new Big(y)).s;
			if (a != b) {
				y.s = -b;
				return x.plus(y);
			}
			var xc = x.c.slice(), xe = x.e, yc = y.c, ye = y.e;
			if (!xc[0] || !yc[0]) {
				if (yc[0]) y.s = -b;
				else if (xc[0]) y = new Big(x);
				else y.s = 1;
				return y;
			}
			if (a = xe - ye) {
				if (xlty = a < 0) {
					a = -a;
					t = xc;
				} else {
					ye = xe;
					t = yc;
				}
				t.reverse();
				for (b = a; b--;) t.push(0);
				t.reverse();
			} else {
				j = ((xlty = xc.length < yc.length) ? xc : yc).length;
				for (a = b = 0; b < j; b++) if (xc[b] != yc[b]) {
					xlty = xc[b] < yc[b];
					break;
				}
			}
			if (xlty) {
				t = xc;
				xc = yc;
				yc = t;
				y.s = -y.s;
			}
			if ((b = (j = yc.length) - (i = xc.length)) > 0) for (; b--;) xc[i++] = 0;
			for (b = i; j > a;) {
				if (xc[--j] < yc[j]) {
					for (i = j; i && !xc[--i];) xc[i] = 9;
					--xc[i];
					xc[j] += 10;
				}
				xc[j] -= yc[j];
			}
			for (; xc[--b] === 0;) xc.pop();
			for (; xc[0] === 0;) {
				xc.shift();
				--ye;
			}
			if (!xc[0]) {
				y.s = 1;
				xc = [ye = 0];
			}
			y.c = xc;
			y.e = ye;
			return y;
		};
		P.mod = function(y) {
			var ygtx, x = this, Big = x.constructor, a = x.s, b = (y = new Big(y)).s;
			if (!y.c[0]) throw Error(DIV_BY_ZERO);
			x.s = y.s = 1;
			ygtx = y.cmp(x) == 1;
			x.s = a;
			y.s = b;
			if (ygtx) return new Big(x);
			a = Big.DP;
			b = Big.RM;
			Big.DP = Big.RM = 0;
			x = x.div(y);
			Big.DP = a;
			Big.RM = b;
			return this.minus(x.times(y));
		};
		P.neg = function() {
			var x = new this.constructor(this);
			x.s = -x.s;
			return x;
		};
		P.plus = P.add = function(y) {
			var e, k, t, x = this, Big = x.constructor;
			y = new Big(y);
			if (x.s != y.s) {
				y.s = -y.s;
				return x.minus(y);
			}
			var xe = x.e, xc = x.c, ye = y.e, yc = y.c;
			if (!xc[0] || !yc[0]) {
				if (!yc[0]) if (xc[0]) y = new Big(x);
				else y.s = x.s;
				return y;
			}
			xc = xc.slice();
			if (e = xe - ye) {
				if (e > 0) {
					ye = xe;
					t = yc;
				} else {
					e = -e;
					t = xc;
				}
				t.reverse();
				for (; e--;) t.push(0);
				t.reverse();
			}
			if (xc.length - yc.length < 0) {
				t = yc;
				yc = xc;
				xc = t;
			}
			e = yc.length;
			for (k = 0; e; xc[e] %= 10) k = (xc[--e] = xc[e] + yc[e] + k) / 10 | 0;
			if (k) {
				xc.unshift(k);
				++ye;
			}
			for (e = xc.length; xc[--e] === 0;) xc.pop();
			y.c = xc;
			y.e = ye;
			return y;
		};
		P.pow = function(n) {
			var x = this, one = new x.constructor("1"), y = one, isneg = n < 0;
			if (n !== ~~n || n < -MAX_POWER || n > MAX_POWER) throw Error(INVALID + "exponent");
			if (isneg) n = -n;
			for (;;) {
				if (n & 1) y = y.times(x);
				n >>= 1;
				if (!n) break;
				x = x.times(x);
			}
			return isneg ? one.div(y) : y;
		};
		P.prec = function(sd, rm) {
			if (sd !== ~~sd || sd < 1 || sd > MAX_DP) throw Error(INVALID + "precision");
			return round(new this.constructor(this), sd, rm);
		};
		P.round = function(dp, rm) {
			if (dp === UNDEFINED) dp = 0;
			else if (dp !== ~~dp || dp < -MAX_DP || dp > MAX_DP) throw Error(INVALID_DP);
			return round(new this.constructor(this), dp + this.e + 1, rm);
		};
		P.sqrt = function() {
			var r, c, t, x = this, Big = x.constructor, s = x.s, e = x.e, half = new Big("0.5");
			if (!x.c[0]) return new Big(x);
			if (s < 0) throw Error(NAME + "No square root");
			s = Math.sqrt(+stringify(x, true, true));
			if (s === 0 || s === Infinity) {
				c = x.c.join("");
				if (!(c.length + e & 1)) c += "0";
				s = Math.sqrt(c);
				e = ((e + 1) / 2 | 0) - (e < 0 || e & 1);
				r = new Big((s == Infinity ? "5e" : (s = s.toExponential()).slice(0, s.indexOf("e") + 1)) + e);
			} else r = new Big(s + "");
			e = r.e + (Big.DP += 4);
			do {
				t = r;
				r = half.times(t.plus(x.div(t)));
			} while (t.c.slice(0, e).join("") !== r.c.slice(0, e).join(""));
			return round(r, (Big.DP -= 4) + r.e + 1, Big.RM);
		};
		P.times = P.mul = function(y) {
			var c, x = this, Big = x.constructor, xc = x.c, yc = (y = new Big(y)).c, a = xc.length, b = yc.length, i = x.e, j = y.e;
			y.s = x.s == y.s ? 1 : -1;
			if (!xc[0] || !yc[0]) {
				y.c = [y.e = 0];
				return y;
			}
			y.e = i + j;
			if (a < b) {
				c = xc;
				xc = yc;
				yc = c;
				j = a;
				a = b;
				b = j;
			}
			for (c = new Array(j = a + b); j--;) c[j] = 0;
			for (i = b; i--;) {
				b = 0;
				for (j = a + i; j > i;) {
					b = c[j] + yc[i] * xc[j - i - 1] + b;
					c[j--] = b % 10;
					b = b / 10 | 0;
				}
				c[j] = b;
			}
			if (b) ++y.e;
			else c.shift();
			for (i = c.length; !c[--i];) c.pop();
			y.c = c;
			return y;
		};
		P.toExponential = function(dp, rm) {
			var x = this, n = x.c[0];
			if (dp !== UNDEFINED) {
				if (dp !== ~~dp || dp < 0 || dp > MAX_DP) throw Error(INVALID_DP);
				x = round(new x.constructor(x), ++dp, rm);
				for (; x.c.length < dp;) x.c.push(0);
			}
			return stringify(x, true, !!n);
		};
		P.toFixed = function(dp, rm) {
			var x = this, n = x.c[0];
			if (dp !== UNDEFINED) {
				if (dp !== ~~dp || dp < 0 || dp > MAX_DP) throw Error(INVALID_DP);
				x = round(new x.constructor(x), dp + x.e + 1, rm);
				for (dp = dp + x.e + 1; x.c.length < dp;) x.c.push(0);
			}
			return stringify(x, false, !!n);
		};
		P.toJSON = P.toString = function() {
			var x = this, Big = x.constructor;
			return stringify(x, x.e <= Big.NE || x.e >= Big.PE, !!x.c[0]);
		};
		if (typeof Symbol !== "undefined") P[Symbol.for("nodejs.util.inspect.custom")] = P.toJSON;
		P.toNumber = function() {
			var n = +stringify(this, true, true);
			if (this.constructor.strict === true && !this.eq(n.toString())) throw Error(NAME + "Imprecise conversion");
			return n;
		};
		P.toPrecision = function(sd, rm) {
			var x = this, Big = x.constructor, n = x.c[0];
			if (sd !== UNDEFINED) {
				if (sd !== ~~sd || sd < 1 || sd > MAX_DP) throw Error(INVALID + "precision");
				x = round(new Big(x), sd, rm);
				for (; x.c.length < sd;) x.c.push(0);
			}
			return stringify(x, sd <= x.e || x.e <= Big.NE || x.e >= Big.PE, !!n);
		};
		P.valueOf = function() {
			var x = this, Big = x.constructor;
			if (Big.strict === true) throw Error(NAME + "valueOf disallowed");
			return stringify(x, x.e <= Big.NE || x.e >= Big.PE, true);
		};
		var Big = _Big_();
		//#endregion
		//#region \0dsh-css:/home/runner/work/deepseek-harness/deepseek-harness/packages/client/ui-settings-account/src/client/PlatformOverlay.module.css.mjs
		const css$1 = "._44HXVa_overlay{z-index:1001;background:var(--dsw-alias-bg-base);flex-direction:column;display:flex;position:fixed;inset:0}[data-windows-titlebar] ._44HXVa_overlay{padding-top:var(--dsh-windows-titlebar-height)}._44HXVa_header{box-sizing:border-box;border-bottom:.5px solid var(--dsw-alias-border-l1);app-region:drag;flex:none;height:48px;padding:6px 16px}._44HXVa_controls{align-items:center;gap:24px;padding-top:5px;display:flex}._44HXVa_trafficLights{flex:none;width:60.667px;height:14px;display:none}html[data-platform=darwin] ._44HXVa_trafficLights{display:block}._44HXVa_back{box-sizing:border-box;height:28px;color:var(--dsw-alias-label-secondary);font:inherit;white-space:nowrap;cursor:pointer;app-region:no-drag;background:0 0;border:none;border-radius:28px;justify-content:center;align-items:center;gap:8px;padding:0 6px;font-size:14px;line-height:22px;display:inline-flex}._44HXVa_viewport{min-height:0;color:var(--dsw-alias-label-secondary);flex:1;position:relative}._44HXVa_status{flex-direction:column;justify-content:center;align-items:center;gap:16px;display:flex;position:absolute;inset:0}._44HXVa_failure{color:var(--dsw-alias-label-tertiary);text-align:center;font-size:14px;line-height:22px}._44HXVa_retry._44HXVa_retry{box-sizing:border-box;border:.5px solid var(--dsw-alias-border-l2);border-radius:18px;min-width:58px;height:32px;padding:0 12px;font-size:13px;font-weight:400;line-height:20px}._44HXVa_spinner{width:24px;height:24px;animation:1s linear infinite _44HXVa_spin;position:relative}._44HXVa_spinner:before{content:\"\";background:url(data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMTkiIGhlaWdodD0iMjIiIHZpZXdCb3g9IjAgMCAxOSAyMiIgZmlsbD0ibm9uZSIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj4KPGcgY2xpcC1wYXRoPSJ1cmwoI3BhaW50MF9hbmd1bGFyXzI5ODhfMzIzMjlfY2xpcF9wYXRoKSIgZGF0YS1maWdtYS1za2lwLXBhcnNlPSJ0cnVlIj48ZyB0cmFuc2Zvcm09Im1hdHJpeCgwLjAwNjk1MDQ4IDAuMDA2OTUwNDggLTAuMDA2OTUwNDggMC4wMDY5NTA0OCAxMC44Nzk3IDEwLjg3OTMpIj48Zm9yZWlnbk9iamVjdCB4PSItMTg2Ny40MiIgeT0iLTE4NjcuNDIiIHdpZHRoPSIzNzM0Ljg1IiBoZWlnaHQ9IjM3MzQuODUiPjxkaXYgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzE5OTkveGh0bWwiIHN0eWxlPSJiYWNrZ3JvdW5kOmNvbmljLWdyYWRpZW50KGZyb20gOTBkZWcscmdiYSgyNDYsIDI0NiwgMjQ2LCAwLjk5NDMpIDBkZWcscmdiYSgwLCAwLCAwLCAwLjgzKSAyNzMuMDI3ZGVnLHJnYmEoMCwgMCwgMCwgMCkgMjg3LjY5NGRlZyxyZ2JhKDI1NSwgMjU1LCAyNTUsIDEpIDM1MC40OTdkZWcscmdiYSgyNDYsIDI0NiwgMjQ2LCAwLjk5NDMpIDM2MGRlZyk7aGVpZ2h0OjEwMCU7d2lkdGg6MTAwJTtvcGFjaXR5OjAuNSI+PC9kaXY+PC9mb3JlaWduT2JqZWN0PjwvZz48L2c+PHBhdGggZD0iTTMuMTg2MjcgMTguNTcyMkMtMS4wNjIwOSAxNC4zMjM2IC0xLjA2MjA5IDcuNDM1MDIgMy4xODYyNyAzLjE4NjM5QzcuNDM0ODggLTEuMDYyMjIgMTQuMzIzMyAtMS4wNjIwNSAxOC41NzIxIDMuMTg2MzlMMTcuMDg3OCA0LjY3MDdDMTMuNjU5MSAxLjI0MjM2IDguMTAwMTEgMS4yNDMyMiA0LjY3MTYxIDQuNjcxNzNDMS4yNDMzNSA4LjEwMDI2IDEuMjQzMzUgMTMuNjU4MyA0LjY3MTYxIDE3LjA4NjhDOC4xMDAxMSAyMC41MTUzIDEzLjY1OTEgMjAuNTE2MiAxNy4wODc4IDE3LjA4NzlMMTguNTcyMSAxOC41NzIyQzE0LjMyMzMgMjIuODIwNiA3LjQzNDg4IDIyLjgyMDggMy4xODYyNyAxOC41NzIyWiIgZGF0YS1maWdtYS1ncmFkaWVudC1maWxsPSJ7JiMzNDt0eXBlJiMzNDs6JiMzNDtHUkFESUVOVF9BTkdVTEFSJiMzNDssJiMzNDtzdG9wcyYjMzQ7Olt7JiMzNDtjb2xvciYjMzQ7OnsmIzM0O3ImIzM0OzowLjAsJiMzNDtnJiMzNDs6MC4wLCYjMzQ7YiYjMzQ7OjAuMCwmIzM0O2EmIzM0OzowLjgyOTk5OTk4MzMxMDY5OTQ2fSwmIzM0O3Bvc2l0aW9uJiMzNDs6MC43NTg0MDg3MjUyNjE2ODgyM30seyYjMzQ7Y29sb3ImIzM0Ozp7JiMzNDtyJiMzNDs6MC4wLCYjMzQ7ZyYjMzQ7OjAuMCwmIzM0O2ImIzM0OzowLjAsJiMzNDthJiMzNDs6MC4wfSwmIzM0O3Bvc2l0aW9uJiMzNDs6MC43OTkxNDk2OTIwNTg1NjMyM30seyYjMzQ7Y29sb3ImIzM0Ozp7JiMzNDtyJiMzNDs6MS4wLCYjMzQ7ZyYjMzQ7OjEuMCwmIzM0O2ImIzM0OzoxLjAsJiMzNDthJiMzNDs6MS4wfSwmIzM0O3Bvc2l0aW9uJiMzNDs6MC45NzM2MDE4MTgwODQ3MTY4MH1dLCYjMzQ7dHJhbnNmb3JtJiMzNDs6eyYjMzQ7bTAwJiMzNDs6MTMuOTAwOTUzMjkyODQ2NjgwLCYjMzQ7bTAxJiMzNDs6LTEzLjkwMDk1MzI5Mjg0NjY4MCwmIzM0O20wMiYjMzQ7OjEwLjg3OTY3Nzc3MjUyMTk3MywmIzM0O20xMCYjMzQ7OjEzLjkwMDk1NDI0NjUyMDk5NiwmIzM0O20xMSYjMzQ7OjEzLjkwMDk1NDI0NjUyMDk5NiwmIzM0O20xMiYjMzQ7Oi0zLjAyMTY2NzAwMzYzMTU5MTh9LCYjMzQ7b3BhY2l0eSYjMzQ7OjAuNTAsJiMzNDtibGVuZE1vZGUmIzM0OzomIzM0O05PUk1BTCYjMzQ7LCYjMzQ7c3RvcHNWYXImIzM0OzpbeyYjMzQ7Y29sb3ImIzM0Ozp7JiMzNDtyJiMzNDs6MC4wLCYjMzQ7ZyYjMzQ7OjAuMCwmIzM0O2ImIzM0OzowLjAsJiMzNDthJiMzNDs6MC44Mjk5OTk5ODMzMTA2OTk0Nn0sJiMzNDtwb3NpdGlvbiYjMzQ7OjAuNzU4NDA4NzI1MjYxNjg4MjN9LHsmIzM0O2NvbG9yJiMzNDs6eyYjMzQ7ciYjMzQ7OjAuMCwmIzM0O2cmIzM0OzowLjAsJiMzNDtiJiMzNDs6MC4wLCYjMzQ7YSYjMzQ7OjAuMH0sJiMzNDtwb3NpdGlvbiYjMzQ7OjAuNzk5MTQ5NjkyMDU4NTYzMjN9LHsmIzM0O2NvbG9yJiMzNDs6eyYjMzQ7ciYjMzQ7OjEuMCwmIzM0O2cmIzM0OzoxLjAsJiMzNDtiJiMzNDs6MS4wLCYjMzQ7YSYjMzQ7OjEuMH0sJiMzNDtwb3NpdGlvbiYjMzQ7OjAuOTczNjAxODE4MDg0NzE2ODB9XSwmIzM0O3Zpc2libGUmIzM0Ozp0cnVlfSIvPgo8ZGVmcz4KPGNsaXBQYXRoIGlkPSJwYWludDBfYW5ndWxhcl8yOTg4XzMyMzI5X2NsaXBfcGF0aCI+PHBhdGggZD0iTTMuMTg2MjcgMTguNTcyMkMtMS4wNjIwOSAxNC4zMjM2IC0xLjA2MjA5IDcuNDM1MDIgMy4xODYyNyAzLjE4NjM5QzcuNDM0ODggLTEuMDYyMjIgMTQuMzIzMyAtMS4wNjIwNSAxOC41NzIxIDMuMTg2MzlMMTcuMDg3OCA0LjY3MDdDMTMuNjU5MSAxLjI0MjM2IDguMTAwMTEgMS4yNDMyMiA0LjY3MTYxIDQuNjcxNzNDMS4yNDMzNSA4LjEwMDI2IDEuMjQzMzUgMTMuNjU4MyA0LjY3MTYxIDE3LjA4NjhDOC4xMDAxMSAyMC41MTUzIDEzLjY1OTEgMjAuNTE2MiAxNy4wODc4IDE3LjA4NzlMMTguNTcyMSAxOC41NzIyQzE0LjMyMzMgMjIuODIwNiA3LjQzNDg4IDIyLjgyMDggMy4xODYyNyAxOC41NzIyWiIvPjwvY2xpcFBhdGg+PC9kZWZzPgo8L3N2Zz4K) 50%/100% 100% no-repeat;width:18.572px;height:21.759px;position:absolute;top:1.121px;left:1.12px}@keyframes _44HXVa_spin{to{transform:rotate(360deg)}}@media (prefers-reduced-motion:reduce){._44HXVa_spinner{animation:none}}";
		const tagId$1 = "@deepseek-ai/dsh-client-ui-settings-account/PlatformOverlay.module.css";
		if (typeof document !== "undefined" && document.querySelector("style[data-plugin-css=" + JSON.stringify(tagId$1) + "]") === null) {
			const tag = document.createElement("style");
			tag.dataset.plugin = "@deepseek-ai/dsh-client-ui-settings-account";
			tag.dataset.pluginCss = tagId$1;
			tag.textContent = css$1;
			document.head.appendChild(tag);
		}
		var PlatformOverlay_module_css_default = {
			"back": "_44HXVa_back",
			"controls": "_44HXVa_controls",
			"failure": "_44HXVa_failure",
			"header": "_44HXVa_header",
			"overlay": "_44HXVa_overlay",
			"retry": "_44HXVa_retry",
			"spin": "_44HXVa_spin",
			"spinner": "_44HXVa_spinner",
			"status": "_44HXVa_status",
			"trafficLights": "_44HXVa_trafficLights",
			"viewport": "_44HXVa_viewport"
		};
		//#endregion
		//#region lib/types/client/PlatformOverlay.js
		/** Desktop Platform viewport; the native child owns remote content and credentials. */
		/** @param props - native commands, localized copy, and return action. @returns full-window Platform container. */
		function PlatformOverlay({ bridge, page, backLabel, loadingLabel, failureLabel, retryLabel, onClose }) {
			const layer = (0, react.useRef)(null);
			const back = (0, react.useRef)(null);
			const viewport = (0, react.useRef)(null);
			const [attempt, setAttempt] = (0, react.useState)(0);
			const [status, setStatus] = (0, react.useState)("loading");
			(0, react.useEffect)(() => {
				const element = viewport.current;
				const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
				const background = Array.from(document.body.children).filter((element) => element instanceof HTMLElement && element !== layer.current).map((element) => ({
					element,
					inert: element.inert
				}));
				for (const { element } of background) element.inert = true;
				back.current?.focus();
				let closed = false;
				const bounds = () => {
					const rect = element.getBoundingClientRect();
					return {
						x: rect.x,
						y: rect.y,
						width: rect.width,
						height: rect.height
					};
				};
				const fail = () => {
					if (!closed) setStatus("failed");
				};
				setStatus("loading");
				bridge.open(page, bounds()).then(() => {
					if (!closed) setStatus("loaded");
				}, fail);
				const observer = new ResizeObserver(() => {
					bridge.setBounds(bounds()).catch(fail);
				});
				observer.observe(element);
				return () => {
					closed = true;
					observer.disconnect();
					for (const { element, inert } of background) element.inert = inert;
					if (previousFocus?.isConnected) previousFocus.focus();
					bridge.close().catch(() => {});
				};
			}, [
				bridge,
				page,
				attempt
			]);
			return (0, react_dom.createPortal)((0, react_jsx_runtime.jsxs)("div", {
				ref: layer,
				className: PlatformOverlay_module_css_default.overlay,
				role: "dialog",
				"aria-modal": "true",
				"aria-label": backLabel,
				children: [(0, react_jsx_runtime.jsx)("header", {
					className: PlatformOverlay_module_css_default.header,
					children: (0, react_jsx_runtime.jsxs)("div", {
						className: PlatformOverlay_module_css_default.controls,
						children: [(0, react_jsx_runtime.jsx)("span", {
							className: PlatformOverlay_module_css_default.trafficLights,
							"aria-hidden": "true"
						}), (0, react_jsx_runtime.jsxs)("button", {
							ref: back,
							className: PlatformOverlay_module_css_default.back,
							onClick: onClose,
							children: [(0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.IconChevronLeftOutlineRegular, { size: 16 }), backLabel]
						})]
					})
				}), (0, react_jsx_runtime.jsx)("div", {
					ref: viewport,
					className: PlatformOverlay_module_css_default.viewport,
					children: status !== "loaded" && (0, react_jsx_runtime.jsx)("div", {
						className: PlatformOverlay_module_css_default.status,
						role: "status",
						"aria-label": status === "loading" ? loadingLabel : void 0,
						children: status === "failed" ? (0, react_jsx_runtime.jsxs)(react_jsx_runtime.Fragment, { children: [(0, react_jsx_runtime.jsx)("span", {
							className: PlatformOverlay_module_css_default.failure,
							children: failureLabel
						}), (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.Button, {
							variant: "outline",
							className: PlatformOverlay_module_css_default.retry,
							onClick: () => {
								setAttempt((value) => value + 1);
							},
							children: retryLabel
						})] }) : (0, react_jsx_runtime.jsx)("span", {
							className: PlatformOverlay_module_css_default.spinner,
							"aria-hidden": "true"
						})
					})
				})]
			}), document.body);
		}
		//#endregion
		//#region lib/types/client/formatBalance.js
		/** Platform Web currency formatting for account balances; source amounts retain decimal precision. */
		/**
		* Format a balance using Platform Web's two-decimal and sub-cent display rules.
		* @param amount - validated decimal balance string.
		* @param symbol - currency symbol.
		* @returns signed currency text with grouped digits.
		*/
		function formatBalance(amount, symbol) {
			const value = new Big(amount);
			if (value.eq(0)) return `${symbol}0.00`;
			if (value.lt(0)) return `-${symbol}${value.gt(-.01) ? "0.01" : addCommas(value.abs().toFixed(2))}`;
			if (value.lt("0.01")) return `<${symbol}0.01`;
			return `${symbol}${addCommas(value.round(2, Big.roundDown).toFixed(2))}`;
		}
		function addCommas(value) {
			const [integer, fraction] = value.split(".");
			return `${Number(integer).toLocaleString()}.${fraction}`;
		}
		//#endregion
		//#region \0dsh-css:/home/runner/work/deepseek-harness/deepseek-harness/packages/client/ui-settings-account/src/client/AccountSection.module.css.mjs
		const css = ".LcmJYa_section{color:var(--dsw-alias-label-primary);flex-direction:column;gap:16px;padding:8px 0;font-size:13px;line-height:22px;display:flex}.LcmJYa_card,.LcmJYa_balanceCard{border:.5px solid var(--dsw-alias-border-l2);background:var(--dsw-alias-bg-module-platform);border-radius:10px;padding:12px 16px}.LcmJYa_card,.LcmJYa_row{justify-content:space-between;align-items:center;gap:16px;display:flex}.LcmJYa_identity{align-items:center;gap:10px;min-width:0;min-height:44px;display:flex}.LcmJYa_avatar{width:32px;height:32px;color:var(--dsw-alias-label-tertiary);background:var(--dsw-alias-bg-skeleton);border-radius:16px;flex:none;justify-content:center;align-items:center;display:flex}.LcmJYa_identityCopy{flex-direction:column;min-width:0;display:flex}.LcmJYa_name{font-size:14px;font-weight:500}.LcmJYa_status,.LcmJYa_secondary,.LcmJYa_unavailable{color:var(--dsw-alias-label-tertiary)}.LcmJYa_balanceCard{flex-direction:column;gap:8px;display:flex}.LcmJYa_row{box-sizing:border-box;min-height:40px;padding:6px 0}.LcmJYa_divider{border-top:.5px solid var(--dsw-alias-border-l2)}.LcmJYa_links,.LcmJYa_actions{flex-wrap:wrap;justify-content:flex-end;align-items:center;gap:10px;display:flex}.LcmJYa_button.LcmJYa_button,.LcmJYa_linkButton{box-sizing:border-box;border:.5px solid var(--dsw-alias-border-l2);white-space:nowrap;border-radius:12px;flex:none;justify-content:center;align-items:center;min-width:58px;height:32px;padding:0 12px;font-size:13px;line-height:20px;text-decoration:none;display:inline-flex}.LcmJYa_linkButton{color:var(--dsw-alias-label-primary)}.LcmJYa_linkButton:hover{background:var(--dsw-alias-interactive-bg-hover)}.LcmJYa_linkButton:focus-visible{outline:2px solid var(--dsw-alias-button-primary-fill);outline-offset:2px}.LcmJYa_primary{color:var(--dsw-alias-label-primary-foreground);background:var(--dsw-alias-button-primary-fill);border-color:#0000;font-weight:500}.LcmJYa_primary:hover{background:var(--dsw-alias-button-primary-hover)}.LcmJYa_signedOut{box-sizing:border-box;min-height:calc(100% + 16px);color:var(--dsw-alias-label-primary);flex-direction:column;justify-content:center;align-items:center;margin-bottom:-16px;padding-bottom:8px;display:flex}.LcmJYa_signedOutContent{flex-direction:column;justify-content:center;align-items:center;gap:20px;width:100%;min-height:60px;padding:12px 0;display:flex}.LcmJYa_signedOutCopy{text-align:center;flex-direction:column;gap:4px;width:100%;display:flex}.LcmJYa_signedOutTitle{font-size:14px;line-height:22px}.LcmJYa_signedOutDescription{color:var(--dsw-alias-label-tertiary);font-size:12px;line-height:18px}.LcmJYa_signInButton.LcmJYa_signInButton{border-radius:12px;min-width:72px;height:36px;padding:0 14px;font-size:14px;font-weight:500;line-height:22px}.LcmJYa_amount{flex-wrap:wrap;justify-content:flex-end;font-size:18px;font-weight:510;line-height:28px;display:flex}.LcmJYa_amount>span+span:before{content:\" + \";white-space:pre}.LcmJYa_accountInfo{color:var(--dsw-alias-label-primary);flex:none;align-items:center;gap:2px;font-size:13px;line-height:22px;text-decoration:underline;display:inline-flex}";
		const tagId = "@deepseek-ai/dsh-client-ui-settings-account/AccountSection.module.css";
		if (typeof document !== "undefined" && document.querySelector("style[data-plugin-css=" + JSON.stringify(tagId) + "]") === null) {
			const tag = document.createElement("style");
			tag.dataset.plugin = "@deepseek-ai/dsh-client-ui-settings-account";
			tag.dataset.pluginCss = tagId;
			tag.textContent = css;
			document.head.appendChild(tag);
		}
		var AccountSection_module_css_default = {
			"accountInfo": "LcmJYa_accountInfo",
			"actions": "LcmJYa_actions",
			"amount": "LcmJYa_amount",
			"avatar": "LcmJYa_avatar",
			"balanceCard": "LcmJYa_balanceCard",
			"button": "LcmJYa_button",
			"card": "LcmJYa_card",
			"divider": "LcmJYa_divider",
			"identity": "LcmJYa_identity",
			"identityCopy": "LcmJYa_identityCopy",
			"linkButton": "LcmJYa_linkButton",
			"links": "LcmJYa_links",
			"name": "LcmJYa_name",
			"primary": "LcmJYa_primary",
			"row": "LcmJYa_row",
			"secondary": "LcmJYa_secondary",
			"section": "LcmJYa_section",
			"signInButton": "LcmJYa_signInButton",
			"signedOut": "LcmJYa_signedOut",
			"signedOutContent": "LcmJYa_signedOutContent",
			"signedOutCopy": "LcmJYa_signedOutCopy",
			"signedOutDescription": "LcmJYa_signedOutDescription",
			"signedOutTitle": "LcmJYa_signedOutTitle",
			"status": "LcmJYa_status",
			"unavailable": "LcmJYa_unavailable"
		};
		//#endregion
		//#region lib/types/client/AccountSection.js
		/** Account settings renders safe Host state and explicit login actions. */
		/** @param props - localized actions and account subscription. @returns account settings UI. */
		function AccountSection({ t, useAccount, useTheme, start, cancel, refresh, platform }) {
			const { view: state, details, failed: streamFailed } = useAccount((value) => value);
			const colorScheme = useTheme((snapshot) => snapshot.active.colorScheme);
			const [platformPage, setPlatformPage] = (0, react.useState)();
			const [failed, setFailed] = (0, react.useState)(false);
			const [busy, setBusy] = (0, react.useState)(false);
			(0, react.useEffect)(() => {
				refresh();
			}, [refresh]);
			const profile = details?.profile?.status === "ready" ? details.profile.value : void 0;
			const wallets = details?.balance?.status === "ready" ? details.balance.value : void 0;
			const bonusWallets = details?.balance?.status === "ready" ? details.balance.bonusWallets.filter((wallet) => new Big(wallet.balance).gt(0)) : [];
			const attempt = state?.attempt;
			const active = attempt !== null && attempt !== void 0 && [
				"initializing",
				"waiting-browser",
				"exchanging",
				"committing"
			].includes(attempt.phase);
			const signedIn = state?.status === "credential-stored";
			(0, react.useEffect)(() => {
				if (!signedIn) setPlatformPage(void 0);
			}, [signedIn]);
			const run = async (action) => {
				setBusy(true);
				setFailed(false);
				try {
					await action();
				} catch {
					setFailed(true);
				} finally {
					setBusy(false);
				}
			};
			const status = failed || streamFailed || attempt?.phase === "failed" ? t("failed") : attempt?.phase === "expired" ? t("expired") : active ? t(attempt.phase === "initializing" ? "initializing" : attempt.phase === "waiting-browser" ? "waiting" : "completing") : signedIn ? profile?.contact ?? t(details?.profile === void 0 ? "loading" : "profileUnavailable") : t("signInDescription");
			if (!signedIn && !active) return (0, react_jsx_runtime.jsx)("section", {
				className: AccountSection_module_css_default.signedOut,
				"aria-label": t("nav"),
				children: (0, react_jsx_runtime.jsxs)("div", {
					className: AccountSection_module_css_default.signedOutContent,
					children: [(0, react_jsx_runtime.jsxs)("div", {
						className: AccountSection_module_css_default.signedOutCopy,
						children: [(0, react_jsx_runtime.jsx)("span", {
							className: AccountSection_module_css_default.signedOutTitle,
							children: t("settingsSignedOutTitle")
						}), (0, react_jsx_runtime.jsx)("span", {
							className: AccountSection_module_css_default.signedOutDescription,
							role: "status",
							children: failed || streamFailed ? t("failed") : t("settingsSignedOutDescription")
						})]
					}), (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.Button, {
						variant: "primary",
						className: AccountSection_module_css_default.signInButton,
						disabled: busy || state === void 0,
						onClick: () => {
							run(start);
						},
						children: t("signIn")
					})]
				})
			});
			return (0, react_jsx_runtime.jsxs)("section", {
				className: AccountSection_module_css_default.section,
				"aria-label": t("nav"),
				children: [
					platformPage !== void 0 && platform !== void 0 && signedIn && (0, react_jsx_runtime.jsx)(PlatformOverlay, {
						bridge: platform,
						page: platformPage,
						backLabel: t("backToHarness"),
						loadingLabel: t("loading"),
						failureLabel: t("platformFailed"),
						retryLabel: t("platformRetry"),
						onClose: () => {
							setPlatformPage(void 0);
						}
					}),
					(0, react_jsx_runtime.jsxs)("div", {
						className: AccountSection_module_css_default.card,
						children: [(0, react_jsx_runtime.jsxs)("div", {
							className: AccountSection_module_css_default.identity,
							children: [(0, react_jsx_runtime.jsx)("span", {
								className: AccountSection_module_css_default.avatar,
								children: (0, react_jsx_runtime.jsx)(AccountAvatar, { url: signedIn ? profile?.avatarUrl : null })
							}), (0, react_jsx_runtime.jsxs)("div", {
								className: AccountSection_module_css_default.identityCopy,
								children: [(0, react_jsx_runtime.jsx)("span", {
									className: AccountSection_module_css_default.name,
									children: signedIn ? profile?.name ?? t("signedIn") : t("signedOut")
								}), (0, react_jsx_runtime.jsx)("span", {
									className: AccountSection_module_css_default.status,
									role: "status",
									children: status
								})]
							})]
						}), signedIn && (0, react_jsx_runtime.jsxs)("a", {
							className: AccountSection_module_css_default.accountInfo,
							href: "https://platform.deepseek.com",
							target: "_blank",
							rel: "noopener noreferrer",
							children: [t("accountInfo"), (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.IconRightUpOutlineRegular, { size: 12 })]
						})]
					}),
					active && (0, react_jsx_runtime.jsxs)("div", {
						className: AccountSection_module_css_default.actions,
						children: [attempt.authorizeUrl && (0, react_jsx_runtime.jsx)("a", {
							className: AccountSection_module_css_default.linkButton,
							href: authorizeUrlWithTheme(attempt.authorizeUrl, colorScheme),
							target: "_blank",
							rel: "noreferrer",
							children: t("open")
						}), (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.Button, {
							variant: "outline",
							className: AccountSection_module_css_default.button,
							disabled: busy || attempt.phase === "committing",
							onClick: () => {
								run(() => cancel(attempt.id));
							},
							children: t("cancel")
						})]
					}),
					(0, react_jsx_runtime.jsxs)("div", {
						className: AccountSection_module_css_default.balanceCard,
						children: [
							(0, react_jsx_runtime.jsxs)("div", {
								className: AccountSection_module_css_default.row,
								children: [(0, react_jsx_runtime.jsx)("span", { children: t("balance") }), signedIn && wallets !== void 0 && wallets.length > 0 ? (0, react_jsx_runtime.jsx)("span", {
									className: AccountSection_module_css_default.amount,
									children: wallets.map((wallet) => (0, react_jsx_runtime.jsx)("span", { children: formatBalance(wallet.balance, wallet.currency === "CNY" ? "¥" : "$") }, wallet.currency))
								}) : (0, react_jsx_runtime.jsx)("span", {
									className: AccountSection_module_css_default.unavailable,
									children: t(!signedIn ? "balanceSignedOut" : details?.balance === void 0 ? "loading" : "balanceUnavailable")
								})]
							}),
							signedIn && bonusWallets.length > 0 && (0, react_jsx_runtime.jsxs)(react_jsx_runtime.Fragment, { children: [(0, react_jsx_runtime.jsx)("div", { className: AccountSection_module_css_default.divider }), (0, react_jsx_runtime.jsxs)("div", {
								className: AccountSection_module_css_default.row,
								children: [(0, react_jsx_runtime.jsx)("span", { children: t("bonusBalance") }), (0, react_jsx_runtime.jsx)("span", {
									className: AccountSection_module_css_default.amount,
									children: bonusWallets.map((wallet) => (0, react_jsx_runtime.jsx)("span", { children: formatBalance(wallet.balance, wallet.currency === "CNY" ? "¥" : "$") }, wallet.currency))
								})]
							})] }),
							(0, react_jsx_runtime.jsx)("div", { className: AccountSection_module_css_default.divider }),
							(0, react_jsx_runtime.jsxs)("div", {
								className: AccountSection_module_css_default.row,
								children: [(0, react_jsx_runtime.jsx)("span", {
									className: AccountSection_module_css_default.secondary,
									children: t("more")
								}), (0, react_jsx_runtime.jsxs)("div", {
									className: AccountSection_module_css_default.links,
									children: [(0, react_jsx_runtime.jsx)("a", {
										className: AccountSection_module_css_default.linkButton,
										href: state?.links.usageUrl,
										"aria-disabled": state === void 0,
										target: "_blank",
										rel: "noreferrer",
										onClick: (event) => {
											if (platform !== void 0 && signedIn) {
												event.preventDefault();
												setPlatformPage("usage");
											}
										},
										children: t("usage")
									}), (0, react_jsx_runtime.jsx)("a", {
										className: `${AccountSection_module_css_default.linkButton} ${AccountSection_module_css_default.primary}`,
										href: state?.links.topUpUrl,
										"aria-disabled": state === void 0,
										target: "_blank",
										rel: "noreferrer",
										onClick: (event) => {
											if (platform !== void 0 && signedIn) {
												event.preventDefault();
												setPlatformPage("top-up");
											}
										},
										children: t("topUp")
									})]
								})]
							})
						]
					})
				]
			});
		}
		//#endregion
		//#region lib/types/client/locales.js
		/** Account settings copy, owned by the account feature. */
		const en = {
			close: "Close",
			addApiKey: "Add API Key",
			retry: "Sign in again",
			loginTitle: "Start creating",
			loginDescription: "Sign in to create, edit, and share your design projects. Everything is saved locally.",
			browserTitle: "Waiting for sign in",
			browserPrompt: "Page did not open automatically? ",
			copyLink: "Copy sign-in link",
			copiedLink: "Link copied",
			copyFailed: "Copy failed",
			browserDescription: ", then open it in your browser to finish signing in.",
			timeoutTitle: "Sign in timed out",
			timeoutDescription: "Sign in again to continue.",
			failureTitle: "Could not sign in",
			platformFailed: "Could not complete the operation. Try again.",
			platformRetry: "Retry",
			loading: "Loading…",
			backToHarness: "Back to DeepSeek Harness",
			settings: "Settings",
			contactUs: "Feedback",
			menu: "Account menu",
			nav: "Account",
			signedIn: "Signed in to DeepSeek",
			signedOut: "Not signed in",
			signIn: "Sign in",
			signOut: "Sign out",
			cancel: "Cancel",
			open: "Open browser",
			initializing: "Starting sign in…",
			waiting: "Continue in your browser",
			completing: "Completing sign in…",
			expired: "Sign in expired. Try again.",
			failed: "Could not complete the operation. Try again.",
			settingsSignedOutTitle: "You are not signed in to DeepSeek Harness",
			settingsSignedOutDescription: "Sign in to DeepSeek Harness to get your dedicated API Key",
			signInDescription: "Use your DeepSeek account to get started.",
			profileUnavailable: "Account details are not available yet.",
			balance: "Recharge balance",
			bonusBalance: "Bonus balance",
			balanceUnavailable: "View on Platform",
			balanceSignedOut: "Sign in to view",
			accountInfo: "More account information",
			more: "More",
			usage: "View usage",
			topUp: "Top up"
		};
		/** Chinese account settings copy. */
		const zh = {
			close: "关闭",
			addApiKey: "添加 API Key",
			retry: "重新登录",
			loginTitle: "开始你的创作",
			loginDescription: "登录后即可创建、编辑和分享你的设计项目，所有内容在本地保存。",
			browserTitle: "等待登录",
			browserPrompt: "没有自动打开新页面？",
			copyLink: "复制登录链接",
			copiedLink: "链接已复制",
			copyFailed: "复制失败",
			browserDescription: "，手动打开登录页完成登录。",
			timeoutTitle: "登录已超时",
			timeoutDescription: "请重新登录后继续操作。",
			failureTitle: "登录失败",
			platformFailed: "操作未完成，请重试",
			platformRetry: "重试",
			loading: "加载中…",
			backToHarness: "返回 DeepSeek Harness",
			settings: "设置",
			contactUs: "意见反馈",
			menu: "账号菜单",
			nav: "账号与余额",
			signedIn: "已登录 DeepSeek",
			signedOut: "尚未登录",
			signIn: "登录",
			signOut: "退出登录",
			cancel: "取消",
			open: "打开浏览器",
			initializing: "正在发起登录…",
			waiting: "请在浏览器中继续",
			completing: "正在完成登录…",
			expired: "登录已过期，请重试。",
			failed: "操作未完成，请重试。",
			settingsSignedOutTitle: "当前未登录 DeepSeek Harness 账号",
			settingsSignedOutDescription: "登录 DeepSeek Harness 账号获取专属 API Key",
			signInDescription: "登录 DeepSeek 账号以开始使用",
			profileUnavailable: "账号资料暂不可用",
			balance: "充值余额",
			bonusBalance: "赠金余额",
			balanceUnavailable: "前往开放平台查看",
			balanceSignedOut: "登录后查看",
			accountInfo: "更多账号信息",
			more: "更多",
			usage: "查询用量",
			topUp: "充值"
		};
		//#endregion
		//#region lib/types/client/index.js
		/** Services required by account settings. */
		const inject = [
			"slots",
			"locale",
			"remote",
			"remote.account",
			"theme"
		];
		/** Register account UI only in the Desktop renderer. @param ctx - client plugin context. */
		function apply(ctx) {
			if (!("dshDesktop" in globalThis)) return;
			ctx.effect(() => ctx.locale.register("settings.account", {
				en,
				zh
			}), "account: dictionaries");
			const t = ctx.locale.bind("settings.account");
			const config = Config(globalThis["__DSH_CONTACT_CONFIG__"] ?? {});
			let snapshot = {
				view: void 0,
				details: void 0,
				failed: false,
				loginVisible: false
			};
			const listeners = /* @__PURE__ */ new Set();
			const publish = (value) => {
				snapshot = value;
				for (const listener of listeners) listener();
			};
			let revision = 0;
			let refreshing;
			const refresh = () => {
				if (snapshot.view?.status !== "credential-stored") return Promise.resolve();
				if (refreshing !== void 0) return refreshing;
				const generation = revision;
				const read = async (field, query) => {
					let value;
					try {
						value = await query();
					} catch {
						value = { status: "failed" };
					}
					if (generation === revision && value !== null) publish({
						...snapshot,
						details: {
							...snapshot.details,
							[field]: value
						}
					});
				};
				const request = Promise.all([read("profile", async () => {
					const result = await ctx.remote.account.getProfile();
					if (!result.ok) throw new Error("account profile failed");
					return result.value;
				}), read("balance", async () => {
					const result = await ctx.remote.account.getBalance();
					if (!result.ok) throw new Error("account balance failed");
					return result.value;
				})]).then(() => void 0);
				refreshing = request;
				request.finally(() => {
					if (refreshing === request) refreshing = void 0;
				});
				return request;
			};
			ctx.effect(() => () => {
				revision++;
			}, "account: details request lifetime");
			const stream = ctx.remote.$stream({
				name: "account",
				open: (signal) => ctx.remote.account.watch(signal),
				ended: () => /* @__PURE__ */ new Error("account stream ended")
			});
			let disposed = false;
			ctx.effect(() => () => {
				disposed = true;
				return stream.dispose();
			}, "account: state stream");
			(async () => {
				for await (const frame of stream) {
					revision++;
					refreshing = void 0;
					publish({
						...snapshot,
						view: frame.value,
						details: void 0,
						failed: false
					});
					frame.accept();
					refresh();
				}
			})().catch(() => {
				if (!disposed) publish({
					...snapshot,
					failed: true
				});
			});
			const nativePlatform = globalThis.dshPlatform;
			const operations = {
				...nativePlatform === void 0 ? {} : { platform: nativePlatform },
				refresh,
				contactUs() {
					const url = contactUrl(config, {
						version: "0.1.7-rc.1",
						locale: ctx.locale.getSnapshot().active === "zh" ? "zh-CN" : "en",
						width: window.screen.width,
						height: window.screen.height,
						pixelRatio: window.devicePixelRatio
					});
					window.open(url, "_blank", "noopener,noreferrer");
				},
				showLogin(visible) {
					publish({
						...snapshot,
						loginVisible: visible
					});
				},
				setOnboarding(active) {
					publish({
						...snapshot,
						onboarding: active
					});
				},
				hooks: {
					account: {
						getSnapshot: () => snapshot,
						subscribe: (listener) => {
							listeners.add(listener);
							return () => {
								listeners.delete(listener);
							};
						}
					},
					theme: {
						getSnapshot: () => ctx.theme.getTheme(),
						subscribe: (listener) => ctx.on("theme/change", listener)
					}
				},
				async start() {
					publish({
						...snapshot,
						loginVisible: true,
						loginFailed: false
					});
					const transport = globalThis.__DSH_TRANSPORT__;
					try {
						if (!(await ctx.remote.account.startSignIn(ctx.locale.getSnapshot().active, transport?.streamBaseUrl !== void 0 ? new URL(transport.streamBaseUrl).origin : window.location.origin, "desktop")).ok) throw new Error("account start failed");
					} catch (error) {
						publish({
							...snapshot,
							loginFailed: true
						});
						throw error;
					}
				},
				async cancel(id) {
					if (!(await ctx.remote.account.cancelSignIn(id)).ok) throw new Error("account cancel failed");
				},
				async signOut() {
					if (!(await ctx.remote.account.signOut()).ok) throw new Error("account sign-out failed");
				}
			};
			ctx.slots.inject("settings.models.sign-in", () => ctx.slots.register({
				name: "settings.models.sign-in",
				locale: "settings.account",
				inject: () => operations
			}, AccountOnboarding));
			ctx.slots.inject("settings.launcher", () => ctx.slots.register({
				name: "settings.launcher",
				locale: "settings.account",
				inject: () => operations
			}, AccountMenu));
			ctx.slots.inject("settings.section", () => {
				let unregister;
				const update = () => {
					if (snapshot.view?.status === "credential-stored") unregister ??= ctx.slots.register({
						name: "settings.section",
						id: "account",
						order: -10,
						label: () => t("nav"),
						locale: "settings.account",
						inject: () => operations
					}, AccountSection);
					else {
						unregister?.();
						unregister = void 0;
					}
				};
				listeners.add(update);
				update();
				return () => {
					listeners.delete(update);
					unregister?.();
				};
			});
		}
		//#endregion
		exports.apply = apply;
		exports.inject = inject;
		return module.exports;
	}
});

//# sourceMappingURL=client.js.map