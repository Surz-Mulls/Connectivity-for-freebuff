package dev.continuity.app.core

import java.io.File
import java.io.FileInputStream
import java.security.MessageDigest

/**
 * Pure-JVM rules for incoming and outgoing transfers. Kept free of Android APIs so the JVM unit
 * tests can exercise the traversal, digest, size and collision cases directly.
 */
object TransferPolicy {
    const val MAX_FILE_SIZE = 8L * 1024 * 1024 * 1024   // 8 GiB, same as the daemon
    const val MAX_CONCURRENT = 4
    const val MAX_NAME = 200

    private val UUID_PATTERN = Regex(
        "^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$"
    )
    private val HEX = "0123456789abcdefABCDEF"

    /** The transfer id becomes part of a filename, so only a canonical UUID is accepted. */
    fun isValidTransferId(id: String): Boolean = id.length == 36 && UUID_PATTERN.matches(id)

    fun isValidSize(size: Long): Boolean = size in 0..MAX_FILE_SIZE

    fun isValidDigest(digest: String): Boolean =
        digest.length == 64 && digest.all { it in HEX }

    /**
     * Returns a safe basename, or null when nothing usable remains. Separators are reduced to a
     * basename (never kept), control characters are dropped, dot-files and Windows device names are
     * refused, and the result is truncated on a character boundary.
     */
    fun safeName(raw: String): String? {
        val base = raw.substringAfterLast('/').substringAfterLast('\\')
        val cleaned = base.filter { !it.isISOControl() }.trim().trim('.')
        if (cleaned.isEmpty() || cleaned.length > MAX_NAME * 2) return null
        val upper = cleaned.substringBefore('.').uppercase()
        if (upper in setOf("CON", "PRN", "AUX", "NUL") ||
            upper.matches(Regex("^(COM|LPT)[1-9]$"))
        ) {
            return null
        }
        return if (cleaned.length <= MAX_NAME) cleaned else cleaned.take(MAX_NAME)
    }

    /** Resolves a non-existing destination inside [root]; appends `-1`, `-2`, … on collision. */
    fun uniqueDestination(root: File, name: String): File? {
        val canonicalRoot = root.canonicalFile
        val stem = name.substringBeforeLast('.', name)
        val suffix = if (name.contains('.')) "." + name.substringAfterLast('.') else ""
        for (index in 0 until 1000) {
            val candidate = File(canonicalRoot, if (index == 0) name else "$stem-$index$suffix")
            if (!isInside(canonicalRoot, candidate)) return null
            if (!candidate.exists()) return candidate
        }
        return null
    }

    /** True only when [child] resolves inside [root] (blocks `..`, absolute names and symlinks). */
    fun isInside(root: File, child: File): Boolean {
        val rootPath = root.canonicalFile.toPath()
        val childPath = child.canonicalFile.toPath()
        return childPath.startsWith(rootPath) && childPath != rootPath
    }

    /** Streams a file once, returning its exact size and lower-case hex SHA-256. */
    fun digestOf(file: File): Pair<Long, String> {
        val digest = MessageDigest.getInstance("SHA-256")
        var total = 0L
        FileInputStream(file).use { input ->
            val buffer = ByteArray(256 * 1024)
            while (true) {
                val read = input.read(buffer)
                if (read < 0) break
                total += read
                digest.update(buffer, 0, read)
            }
        }
        return total to digest.digest().joinToString("") { "%02x".format(it) }
    }
}
