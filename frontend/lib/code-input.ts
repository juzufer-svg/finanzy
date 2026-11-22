/**
 * Lógica compartida de las 6 casillas del código de verificación.
 * Admite escribir dígito a dígito y también que el navegador / teclado del
 * móvil (autocompletado "one-time-code") o un tecleo rápido inserte varios
 * dígitos en una sola casilla: se reparten en las siguientes.
 */
const CODE_LENGTH = 6

export function applyCodeInput(code: string[], index: number, rawValue: string) {
  const digits = rawValue.replace(/\D/g, '')
  const next = [...code]

  const isMulti = digits.length > 2 || (digits.length === 2 && !code[index])
  if (!isMulti) {
    // Un solo dígito nuevo (o borrado): se queda con el último tecleado
    next[index] = digits.slice(-1)
    const focus = next[index] && index < CODE_LENGTH - 1 ? index + 1 : index
    return { code: next, focusIndex: focus }
  }

  const chunk = digits.slice(-(CODE_LENGTH - index))
  for (let k = 0; k < chunk.length; k++) next[index + k] = chunk[k]
  const focus = Math.min(index + chunk.length, CODE_LENGTH - 1)
  return { code: next, focusIndex: focus }
}
