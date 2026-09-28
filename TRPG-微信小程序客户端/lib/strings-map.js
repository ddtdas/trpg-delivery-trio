/**
 * strings-map.js —— 把文案表的键（含 '.'）映射为 WXML 可绑定的标识符，并提供 {占位符} 格式化。
 * 例：'btn.test' -> T.btn_test；format(strings['ext.st.uploadOk'], { bytes: 1024 }) -> '已上传 1024 字节'
 */
const strings = require('../strings')

function map(keys) {
  const source = keys && keys.length ? keys : Object.keys(strings)
  const out = {}
  source.forEach(function (key) {
    out[String(key).replace(/[^A-Za-z0-9]/g, '_')] = strings[key]
  })
  return out
}

/** 填充 {name} 占位符；缺失变量渲染为空串（不抛错、不显示 undefined）。 */
function format(template, vars) {
  return String(template === undefined || template === null ? '' : template)
    .replace(/\{(\w+)\}/g, function (all, name) {
      const value = vars ? vars[name] : undefined
      return value === undefined || value === null ? '' : String(value)
    })
}

module.exports = { map: map, format: format, strings: strings }
