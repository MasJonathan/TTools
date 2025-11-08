/*
  ==============================================================================

	WButton.h
	Created: 7 Nov 2025 11:58:51pm
	Author:  Jonathan

  ==============================================================================
*/

#pragma once
#include "BaseComponent.h"
#include "WLabel.h"


class WButton : public BaseComponent {
public:
	WButton(const String& text) : _text(text) {
		setEditor(true);
		addAndMakeVisible(_text);
	}

private:
	WLabel _text;
};

