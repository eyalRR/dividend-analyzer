import { createClient } from '@supabase/supabase-js'

const supabaseUrl = process.env.REACT_APP_SUPABASE_URL
const supabaseAnonKey = process.env.REACT_APP_SUPABASE_ANON_KEY

export const supabase = createClient(supabaseUrl, supabaseAnonKey)

export const signUp = async (email, password) => {
  try {
    const { user, error } = await supabase.auth.signUp({ email, password })
    if (error) throw error
    return user
  } catch (error) {
    console.error('Error signing up:', error.message)
    throw error
  }
}

export const signIn = async (email, password) => {
  try {
    const { user, error } = await supabase.auth.signInWithPassword({ email, password })
    if (error) throw error
    return user
  } catch (error) {
    console.error('Error signing in:', error.message)
    throw error
  }
}

export const signOut = async () => {
  try {
    const { error } = await supabase.auth.signOut()
    if (error) throw error
  } catch (error) {
    console.error('Error signing out:', error.message)
    throw error
  }
}

export const getCurrentUser = async () => {
  try {
    const { data: { user } } = await supabase.auth.getUser()
    return user
  } catch (error) {
    console.error('Error getting current user:', error.message)
    throw error
  }
}