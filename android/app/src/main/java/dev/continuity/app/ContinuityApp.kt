package dev.continuity.app

import android.app.Application
import dev.continuity.app.core.Store

class ContinuityApp : Application() {
    lateinit var store: Store
        private set

    override fun onCreate() {
        super.onCreate()
        store = Store(this)
    }
}
