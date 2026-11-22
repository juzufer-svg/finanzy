'use client'

import { useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import apiClient from '@/lib/api-client'
import { applyCodeInput } from '@/lib/code-input'
import FinanzyLogo from '@/components/FinanzyLogo'

type Step = 'email' | 'reset' | 'done'

const inputClass =
  'w-full px-4 py-3 border-2 border-gray-200 rounded-lg transition-colors bg-gray-50 focus:bg-white placeholder-gray-400 text-gray-900 focus:outline-none focus:border-[#00B89C]'

const primaryButton =
  'w-full text-white font-bold py-3 px-4 rounded-lg transition-opacity disabled:opacity-60 disabled:cursor-not-allowed shadow-lg flex items-center justify-center gap-2 hover:opacity-95 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#00B89C]'

const MIN_PASSWORD = 8

export default function ForgotPasswordPage() {
  const [step, setStep] = useState<Step>('email')
  const [email, setEmail] = useState('')
  const [code, setCode] = useState(['', '', '', '', '', ''])
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState('')
  const [info, setInfo] = useState('')
  const [loading, setLoading] = useState(false)
  const codeRefs = useRef<(HTMLInputElement | null)[]>([])

  // Al pasar al paso del código, llevar el foco a la primera casilla
  useEffect(() => {
    if (step === 'reset') codeRefs.current[0]?.focus()
  }, [step])

  const requestCode = async (e?: React.FormEvent) => {
    e?.preventDefault()
    setError('')
    setLoading(true)
    try {
      const res = await apiClient.post('/api/v1/auth/forgot-password', { email })
      setInfo(res.data.message)
      setStep('reset')
    } catch (err: any) {
      setError(err.response?.data?.detail?.[0]?.msg ? 'Ingresa un correo válido.' : 'No pudimos enviar el código. Intenta de nuevo en unos minutos.')
    } finally {
      setLoading(false)
    }
  }

  const resetPassword = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    const fullCode = code.join('')
    if (fullCode.length < 6) { setError('Ingresa los 6 dígitos del código.'); return }
    if (password.length < MIN_PASSWORD) { setError(`La contraseña debe tener al menos ${MIN_PASSWORD} caracteres.`); return }
    if (password !== confirm) { setError('Las contraseñas no coinciden.'); return }
    setLoading(true)
    try {
      const res = await apiClient.post('/api/v1/auth/reset-password', {
        email, code: fullCode, new_password: password,
      })
      setInfo(res.data.message)
      setStep('done')
    } catch (err: any) {
      const detail = err.response?.data?.detail
      setError(typeof detail === 'string' ? detail : 'No se pudo cambiar la contraseña. Revisa los datos.')
    } finally {
      setLoading(false)
    }
  }

  const handleCodeInput = (i: number, val: string) => {
    const { code: next, focusIndex } = applyCodeInput(code, i, val)
    setCode(next)
    if (focusIndex !== i) codeRefs.current[focusIndex]?.focus()
  }

  const handleCodeKey = (i: number, e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Backspace' && !code[i] && i > 0) codeRefs.current[i - 1]?.focus()
  }

  const handleCodePaste = (e: React.ClipboardEvent) => {
    const pasted = e.clipboardData.getData('text').replace(/\D/g, '').slice(0, 6)
    if (pasted.length === 6) {
      e.preventDefault()
      setCode(pasted.split(''))
      codeRefs.current[5]?.focus()
    }
  }

  const subtitle = {
    email: 'Recupera el acceso a tu cuenta',
    reset: 'Crea una nueva contraseña',
    done: 'Contraseña actualizada',
  }[step]

  return (
    <>
      <div className="rounded-2xl shadow-2xl overflow-hidden"
           style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(0,184,156,0.25)' }}>
        <div className="px-6 md:px-8 py-8 text-center" style={{ background: 'rgba(13,27,75,0.45)' }}>
          <div className="flex justify-center mb-4">
            <FinanzyLogo variant="full" size={52} lightText />
          </div>
          <h1 className="text-sm md:text-base mt-2 font-medium" style={{ color: '#00B89C' }}>{subtitle}</h1>
        </div>

        <div className="px-6 md:px-8 py-6 md:py-8" style={{ background: 'rgba(255,255,255,0.96)' }}>
          {error && (
            <div role="alert" className="mb-5 p-4 bg-red-50 border-l-4 border-red-500 rounded-lg">
              <p className="text-red-700 text-sm font-medium">{error}</p>
            </div>
          )}
          {info && !error && step !== 'done' && (
            <div role="status" className="mb-5 p-4 bg-teal-50 border-l-4 rounded-lg" style={{ borderColor: '#00B89C' }}>
              <p className="text-sm font-medium" style={{ color: '#0a7a6b' }}>{info}</p>
            </div>
          )}

          {step === 'email' && (
            <form onSubmit={requestCode} className="space-y-5">
              <p className="text-sm text-gray-600">
                Escribe el correo de tu cuenta y te enviaremos un código de 6 dígitos para crear una contraseña nueva.
              </p>
              <div>
                <label htmlFor="fp-email" className="block text-sm font-semibold text-gray-700 mb-2">
                  Correo electrónico
                </label>
                <input
                  id="fp-email" name="email" type="email" autoComplete="email" spellCheck={false} required
                  value={email} onChange={e => setEmail(e.target.value)}
                  placeholder="tu@correo.com" className={inputClass}
                />
              </div>
              <button type="submit" disabled={loading} className={primaryButton}
                      style={{ background: 'linear-gradient(135deg, #0D1B4B 0%, #00B89C 100%)' }}>
                {loading ? 'Enviando…' : 'Enviar código'}
              </button>
            </form>
          )}

          {step === 'reset' && (
            <form onSubmit={resetPassword} className="space-y-5">
              <fieldset>
                <legend className="block text-sm font-semibold text-gray-700 mb-2">
                  Código enviado a <span className="text-gray-900">{email}</span>
                </legend>
                <div className="flex justify-center gap-2" onPaste={handleCodePaste}>
                  {code.map((digit, i) => (
                    <input
                      key={i}
                      ref={el => { codeRefs.current[i] = el }}
                      type="text" inputMode="numeric" spellCheck={false}
                      autoComplete={i === 0 ? 'one-time-code' : 'off'}
                      aria-label={`Dígito ${i + 1} de 6`}
                      value={digit}
                      onChange={e => handleCodeInput(i, e.target.value)}
                      onKeyDown={e => handleCodeKey(i, e)}
                      className="w-11 h-14 text-center text-2xl font-bold border-2 border-gray-200 rounded-xl bg-gray-50 focus:bg-white text-[#0D1B4B] focus:outline-none focus:border-[#00B89C]"
                    />
                  ))}
                </div>
              </fieldset>

              <div>
                <label htmlFor="fp-password" className="block text-sm font-semibold text-gray-700 mb-2">
                  Nueva contraseña
                </label>
                <div className="relative">
                  <input
                    id="fp-password" name="new-password" autoComplete="new-password" required
                    type={showPassword ? 'text' : 'password'} minLength={MIN_PASSWORD}
                    value={password} onChange={e => setPassword(e.target.value)}
                    aria-describedby="fp-password-hint"
                    className={`${inputClass} pr-24`}
                  />
                  <button type="button" onClick={() => setShowPassword(v => !v)}
                          className="absolute inset-y-0 right-0 px-4 text-sm font-semibold text-gray-500 hover:text-gray-700 rounded-r-lg focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#00B89C]"
                          aria-label={showPassword ? 'Ocultar contraseñas' : 'Mostrar contraseñas'}>
                    {showPassword ? 'Ocultar' : 'Mostrar'}
                  </button>
                </div>
                <p id="fp-password-hint" className="mt-1 text-xs text-gray-500">Mínimo {MIN_PASSWORD} caracteres.</p>
              </div>

              <div>
                <label htmlFor="fp-confirm" className="block text-sm font-semibold text-gray-700 mb-2">
                  Confirmar contraseña
                </label>
                <input
                  id="fp-confirm" name="confirm-password" autoComplete="new-password" required
                  type={showPassword ? 'text' : 'password'}
                  value={confirm} onChange={e => setConfirm(e.target.value)}
                  className={inputClass}
                />
              </div>

              <button type="submit" disabled={loading} className={primaryButton}
                      style={{ background: 'linear-gradient(135deg, #0D1B4B 0%, #00B89C 100%)' }}>
                {loading ? 'Guardando…' : 'Cambiar contraseña'}
              </button>

              <div className="flex justify-between text-sm">
                <button type="button" onClick={() => { setStep('email'); setError(''); setInfo(''); setCode(['', '', '', '', '', '']) }}
                        className="text-gray-500 hover:underline rounded focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#00B89C]">
                  ← Cambiar correo
                </button>
                <button type="button" onClick={() => requestCode()} disabled={loading}
                        className="font-semibold hover:underline disabled:opacity-60 rounded focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#00B89C]" style={{ color: '#0a7a6b' }}>
                  Reenviar código
                </button>
              </div>
            </form>
          )}

          {step === 'done' && (
            <div className="space-y-5 text-center" role="status">
              <p className="text-gray-700">{info}</p>
              <Link href="/auth/login" className={primaryButton}
                    style={{ background: 'linear-gradient(135deg, #0D1B4B 0%, #00B89C 100%)' }}>
                Ir a iniciar sesión
              </Link>
            </div>
          )}

          {step !== 'done' && (
            <p className="mt-6 text-center text-sm text-gray-600">
              ¿Recordaste tu contraseña?{' '}
              <Link href="/auth/login" className="font-bold hover:underline" style={{ color: '#0a7a6b' }}>
                Inicia sesión
              </Link>
            </p>
          )}
        </div>
      </div>
    </>
  )
}
