package com.friend.ios.widgets

import org.junit.Assert.assertTrue
import org.junit.Test
import org.w3c.dom.Element
import java.io.File
import javax.xml.parsers.DocumentBuilderFactory

/**
 * Static tripwire for the widget layouts.
 *
 * RemoteViews only inflates a small allowlist of view classes; anything else
 * throws at launcher-inflate time and the home screen shows "Can't load
 * widget". That shipped once because a plain `<View>` (the status dot) is not
 * on the list, and the state/action tests never touched the XML. This parses
 * the shared layout and fails on any disallowed element.
 */
class WidgetLayoutTest {
    private val allowedViews = setOf(
        "FrameLayout",
        "LinearLayout",
        "RelativeLayout",
        "GridLayout",
        "AnalogClock",
        "Button",
        "Chronometer",
        "ImageButton",
        "ImageView",
        "ProgressBar",
        "TextView",
        "ViewFlipper",
        "ListView",
        "GridView",
        "StackView",
        "AdapterViewFlipper",
        "ViewStub",
    )

    @Test
    fun widgetLayoutsOnlyUseRemoteViewsSupportedViews() {
        val layoutDir = listOf(File("src/main/res/layout"), File("app/src/main/res/layout"))
            .firstOrNull { it.isDirectory }
            ?: error("widget layout directory not found")
        val files = layoutDir.listFiles { file -> file.name.startsWith("widget") && file.name.endsWith(".xml") }
            ?: emptyArray()
        assertTrue("no widget layouts found under $layoutDir", files.isNotEmpty())

        val offenders = mutableListOf<String>()
        for (file in files) {
            val document = DocumentBuilderFactory.newInstance().newDocumentBuilder().parse(file)
            val elements = document.getElementsByTagName("*")
            for (index in 0 until elements.length) {
                val tag = (elements.item(index) as Element).tagName.substringAfterLast('.')
                if (tag !in allowedViews) offenders.add("${file.name}:$tag")
            }
        }
        assertTrue("RemoteViews cannot inflate: $offenders", offenders.isEmpty())
    }
}
