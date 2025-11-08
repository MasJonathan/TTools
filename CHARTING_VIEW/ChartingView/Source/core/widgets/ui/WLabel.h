/*
  ==============================================================================

	WLabel.h
	Created: 7 Nov 2025 11:59:22pm
	Author:  Jonathan

  ==============================================================================
*/

#pragma once
#include "BaseComponent.h"

class WLabel : public BaseComponent {
public:
	WLabel(const String& s) : _l("", s) {
		setEditor(false);
		addAndMakeVisible(_l);
		_l.setBorderSize({});
		_l.setInterceptsMouseClicks(false, false);
		_l.setWantsKeyboardFocus(false);
		_l.setJustificationType(Justification::centred);
		_updatePreferredSize(false);
	}

	void paint(Graphics& g) override {
		g.setColour(Colours::white);
		g.drawRect(getLocalBounds());
	}

	void resized() override {
		_updatePreferredSize();
		_l.setBounds(getLocalBounds());
	}

	void setText(const String& s) {
		_l.setText(s, dontSendNotification);
		_updatePreferredSize();
	}

private:

	void _updatePreferredSize(bool notify = true) {
		const int w = _l.getFont().getStringWidth(_l.getText());
		getPreferredSize()
			.setPreferredWidth(w, notify)
			.setPreferredHeight(_l.getFont().getHeight(), notify);
	}

	Label _l;
};

